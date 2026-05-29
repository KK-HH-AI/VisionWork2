import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

EXT_TO_LANGUAGE = {
    '.py': 'python',
    '.pyi': 'python',
    '.js': 'javascript',
    '.mjs': 'javascript',
    '.cjs': 'javascript',
    '.ts': 'typescript',
    '.tsx': 'typescript',
    '.jsx': 'javascript',
}

SUPPORTED_LANGUAGES = set(EXT_TO_LANGUAGE.values())

_LANGUAGE_CACHE: Dict[str, Any] = {}


def _get_language(lang_name: str):
    if lang_name in _LANGUAGE_CACHE:
        return _LANGUAGE_CACHE[lang_name]

    import tree_sitter as ts

    if lang_name == 'python':
        import tree_sitter_python as tspy
        lang = ts.Language(tspy.language())
    elif lang_name == 'javascript':
        import tree_sitter_javascript as tsjs
        lang = ts.Language(tsjs.language())
    elif lang_name == 'typescript':
        import tree_sitter_typescript as tsts
        lang = ts.Language(tsts.language())
    else:
        return None

    _LANGUAGE_CACHE[lang_name] = lang
    return lang


def _get_language_from_filename(filename: str) -> Optional[str]:
    for ext, lang in EXT_TO_LANGUAGE.items():
        if filename.endswith(ext):
            return lang
    return None


def parse_code_entities(code_content: str, language: str) -> Optional[Dict[str, Any]]:
    try:
        lang = _get_language(language)
        if lang is None:
            logger.warning(f"Language '{language}' not supported by tree-sitter")
            return None

        import tree_sitter as ts
        parser = ts.Parser(lang)
        tree = parser.parse(bytes(code_content, 'utf-8'))
        root = tree.root_node

        if root.has_error:
            error_nodes = _count_error_nodes(root)
            if error_nodes > 5:
                logger.warning(
                    f"Parse tree has {error_nodes} error nodes, falling back to LLM extraction"
                )
                return None

        entities = []
        relations = []

        _walk_tree(root, code_content, language, entities, relations,
                   parent_class_id=None, inside_function=False)

        entity_id_set = set()
        deduped_entities = []
        for e in entities:
            eid = e['id']
            if eid not in entity_id_set:
                entity_id_set.add(eid)
                deduped_entities.append(e)

        rel_key_set = set()
        deduped_relations = []
        for r in relations:
            key = (r['source_id'], r['target_id'], r['type'])
            if key not in rel_key_set:
                rel_key_set.add(key)
                deduped_relations.append(r)

        logger.info(
            f"Parsed {len(deduped_entities)} entities and {len(deduped_relations)} relations "
            f"for language '{language}'"
        )

        return {
            'entities': deduped_entities,
            'relations': deduped_relations,
        }
    except Exception as e:
        logger.warning(f"parse_code_entities failed: {type(e).__name__}: {e}")
        return None


def _count_error_nodes(node) -> int:
    count = 0
    if node.has_error:
        count += 1
    for child in node.children:
        count += _count_error_nodes(child)
    return count


def _walk_tree(
    node,
    source: str,
    language: str,
    entities: List[Dict],
    relations: List[Dict],
    parent_class_id: Optional[str],
    inside_function: bool,
    qualifier: str = '',
):
    if not node.is_named:
        return

    node_type = node.type
    line_start = node.start_point[0] + 1
    line_end = node.end_point[0] + 1

    if node_type == 'function_definition':
        name_node = node.child_by_field_name('name')
        if name_node is None:
            return
        name = name_node.text.decode('utf-8')
        qualified_name = f"{qualifier}.{name}" if qualifier else name
        entity_type = 'method' if parent_class_id else 'function'
        entity_id = qualified_name

        entities.append({
            'id': entity_id,
            'type': entity_type,
            'name': name,
            'file': '',
            'line_start': line_start,
            'line_end': line_end,
            'description': '',
        })

        if parent_class_id:
            relations.append({
                'source_id': parent_class_id,
                'target_id': entity_id,
                'type': 'contains',
                'description': '',
            })

        _extract_calls(node, source, entity_id, relations)

        body = node.child_by_field_name('body')
        if body is not None:
            for child in body.named_children:
                _walk_tree(child, source, language, entities, relations,
                           parent_class_id, True, qualifier)

    elif node_type == 'class_definition':
        name_node = node.child_by_field_name('name')
        if name_node is None:
            return
        name = name_node.text.decode('utf-8')
        qualified_name = f"{qualifier}.{name}" if qualifier else name
        entity_id = qualified_name

        entities.append({
            'id': entity_id,
            'type': 'class',
            'name': name,
            'file': '',
            'line_start': line_start,
            'line_end': line_end,
            'description': '',
        })

        superclasses = node.child_by_field_name('superclasses')
        if superclasses is not None:
            for sc_node in superclasses.named_children:
                sc_name = sc_node.text.decode('utf-8')
                if sc_name and sc_name != 'object':
                    relations.append({
                        'source_id': entity_id,
                        'target_id': sc_name,
                        'type': 'inherits',
                        'description': '',
                    })

        _extract_calls(node, source, entity_id, relations)

        body = node.child_by_field_name('body')
        if body is not None:
            for child in body.named_children:
                _walk_tree(child, source, language, entities, relations,
                           entity_id, False, qualifier=qualified_name)

                if child.type == 'expression_statement':
                    _extract_class_member(child, source, entity_id, qualified_name, entities, relations)

    elif node_type == 'function_declaration':
        name_node = node.child_by_field_name('name')
        if name_node is None:
            return
        name = name_node.text.decode('utf-8')
        qualified_name = f"{qualifier}.{name}" if qualifier else name
        entity_type = 'function'
        entity_id = qualified_name

        entities.append({
            'id': entity_id,
            'type': entity_type,
            'name': name,
            'file': '',
            'line_start': line_start,
            'line_end': line_end,
            'description': '',
        })

        _extract_calls(node, source, entity_id, relations)

        body = node.child_by_field_name('body')
        if body is not None:
            for child in body.named_children:
                _walk_tree(child, source, language, entities, relations,
                           parent_class_id, True, qualifier)

    elif node_type == 'generator_function' or node_type == 'generator_function_declaration':
        name_node = node.child_by_field_name('name')
        if name_node is None:
            return
        name = name_node.text.decode('utf-8')
        qualified_name = f"{qualifier}.{name}" if qualifier else name
        entity_type = 'method' if parent_class_id else 'function'
        entity_id = qualified_name

        entities.append({
            'id': entity_id,
            'type': entity_type,
            'name': name,
            'file': '',
            'line_start': line_start,
            'line_end': line_end,
            'description': '',
        })

        if parent_class_id:
            relations.append({
                'source_id': parent_class_id,
                'target_id': entity_id,
                'type': 'contains',
                'description': '',
            })

        _extract_calls(node, source, entity_id, relations)

        body = node.child_by_field_name('body')
        if body is not None:
            for child in body.named_children:
                _walk_tree(child, source, language, entities, relations,
                           parent_class_id, True, qualifier)

    elif node_type == 'method_definition':
        name_node = node.child_by_field_name('name')
        if name_node is None:
            return
        name = name_node.text.decode('utf-8')
        qualified_name = f"{qualifier}.{name}" if qualifier else name
        entity_id = qualified_name

        entities.append({
            'id': entity_id,
            'type': 'method',
            'name': name,
            'file': '',
            'line_start': line_start,
            'line_end': line_end,
            'description': '',
        })

        if parent_class_id:
            relations.append({
                'source_id': parent_class_id,
                'target_id': entity_id,
                'type': 'contains',
                'description': '',
            })

        _extract_calls(node, source, entity_id, relations)

        body = node.child_by_field_name('body')
        if body is not None:
            for child in body.named_children:
                _walk_tree(child, source, language, entities, relations,
                           parent_class_id, True, qualifier)

    elif node_type == 'class_declaration':
        name_node = node.child_by_field_name('name')
        if name_node is None:
            return
        name = name_node.text.decode('utf-8')
        qualified_name = f"{qualifier}.{name}" if qualifier else name
        entity_id = qualified_name

        entities.append({
            'id': entity_id,
            'type': 'class',
            'name': name,
            'file': '',
            'line_start': line_start,
            'line_end': line_end,
            'description': '',
        })

        _extract_js_heritage(node, source, entity_id, relations)

        body = node.child_by_field_name('body')
        if body is not None:
            for child in body.named_children:
                _walk_tree(child, source, language, entities, relations,
                           entity_id, False, qualifier=qualified_name)

    elif node_type == 'variable_declaration' and not inside_function:
        _handle_variable(node, source, qualifier, parent_class_id, entities, relations,
                         line_start, line_end)

    elif node_type == 'lexical_declaration' and not inside_function:
        _handle_lexical(node, source, qualifier, parent_class_id, entities, relations,
                        line_start, line_end)

    elif node_type == 'expression_statement' and not inside_function:
        _handle_expression_statement(node, source, qualifier, parent_class_id, entities, relations,
                                     line_start, line_end)

    elif node_type == 'expression_statement' and inside_function and parent_class_id:
        _extract_class_member(node, source, parent_class_id, qualifier, entities, relations)

    elif node_type == 'import_statement':
        _handle_import_statement(node, source, language, entities, relations)

    elif node_type == 'import_from_statement':
        _handle_import_from(node, source, entities, relations)

    elif node_type == 'export_statement':
        for child in node.named_children:
            _walk_tree(child, source, language, entities, relations,
                       parent_class_id, inside_function, qualifier)

    elif node_type == 'assignment' and not inside_function:
        _handle_assignment(node, source, qualifier, parent_class_id, entities, relations,
                           line_start, line_end)

    elif node_type == 'assignment' and inside_function and parent_class_id:
        _handle_self_assignment(node, source, parent_class_id, qualifier, entities, relations,
                                line_start, line_end)

    elif node_type == 'decorated_definition':
        def_node = None
        for child in node.named_children:
            if child.type in ('function_definition', 'class_definition'):
                def_node = child
                break
        if def_node is not None:
            _walk_tree(def_node, source, language, entities, relations,
                       parent_class_id, inside_function, qualifier)

    elif node_type == 'module':
        for child in node.named_children:
            _walk_tree(child, source, language, entities, relations,
                       None, False, '')

    elif node_type == 'block':
        for child in node.named_children:
            _walk_tree(child, source, language, entities, relations,
                       parent_class_id, inside_function, qualifier)

    elif node_type == 'program':
        for child in node.named_children:
            _walk_tree(child, source, language, entities, relations,
                       None, False, '')

    elif node_type in ('arrow_function', 'function_expression'):
        pass

    else:
        _extract_calls(node, source, parent_class_id, relations)
        for child in node.named_children:
            _walk_tree(child, source, language, entities, relations,
                       parent_class_id, inside_function, qualifier)


def _handle_variable(node, source, qualifier, parent_class_id, entities, relations,
                     line_start, line_end):
    for declarator in node.named_children:
        if declarator.type == 'variable_declarator':
            name_node = declarator.child_by_field_name('name')
            if name_node is None:
                continue
            name = name_node.text.decode('utf-8')
            qualified_name = f"{qualifier}.{name}" if qualifier else name
            entity_id = qualified_name

            entities.append({
                'id': entity_id,
                'type': 'variable',
                'name': name,
                'file': '',
                'line_start': line_start,
                'line_end': line_end,
                'description': '',
            })

            if parent_class_id:
                relations.append({
                    'source_id': parent_class_id,
                    'target_id': entity_id,
                    'type': 'contains',
                    'description': '',
                })

            value = declarator.child_by_field_name('value')
            if value is not None:
                _extract_calls(value, source, entity_id, relations)


def _handle_lexical(node, source, qualifier, parent_class_id, entities, relations,
                    line_start, line_end):
    for declarator in node.named_children:
        if declarator.type == 'variable_declarator':
            name_node = declarator.child_by_field_name('name')
            if name_node is None:
                continue
            name = name_node.text.decode('utf-8')
            qualified_name = f"{qualifier}.{name}" if qualifier else name
            entity_id = qualified_name

            entities.append({
                'id': entity_id,
                'type': 'variable',
                'name': name,
                'file': '',
                'line_start': line_start,
                'line_end': line_end,
                'description': '',
            })

            if parent_class_id:
                relations.append({
                    'source_id': parent_class_id,
                    'target_id': entity_id,
                    'type': 'contains',
                    'description': '',
                })

            value = declarator.child_by_field_name('value')
            if value is not None:
                _extract_calls(value, source, entity_id, relations)


def _handle_expression_statement(node, source, qualifier, parent_class_id, entities, relations,
                                  line_start, line_end):
    for child in node.named_children:
        if child.type == 'assignment':
            _handle_assignment(child, source, qualifier, parent_class_id, entities, relations,
                               line_start, line_end)
        else:
            _extract_calls(child, source, parent_class_id, relations)


def _handle_assignment(node, source, qualifier, parent_class_id, entities, relations,
                       line_start, line_end):
    left = node.child_by_field_name('left')
    if left is None:
        return

    if left.type == 'identifier':
        name = left.text.decode('utf-8')
        if name.startswith('_'):
            return
        qualified_name = f"{qualifier}.{name}" if qualifier else name
        entity_id = qualified_name
        entities.append({
            'id': entity_id,
            'type': 'variable',
            'name': name,
            'file': '',
            'line_start': line_start,
            'line_end': line_end,
            'description': '',
        })
        if parent_class_id:
            relations.append({
                'source_id': parent_class_id,
                'target_id': entity_id,
                'type': 'contains',
                'description': '',
            })

    elif left.type == 'attribute':
        base = left.child_by_field_name('object')
        attr = left.child_by_field_name('attribute')
        if base is not None and attr is not None:
            base_text = base.text.decode('utf-8')
            attr_text = attr.text.decode('utf-8')
            if base_text in ('self', 'this') and parent_class_id:
                member_id = f"{qualifier}.{attr_text}" if qualifier else attr_text
                entities.append({
                    'id': member_id,
                    'type': 'variable',
                    'name': attr_text,
                    'file': '',
                    'line_start': line_start,
                    'line_end': line_end,
                    'description': '',
                })
                relations.append({
                    'source_id': parent_class_id,
                    'target_id': member_id,
                    'type': 'contains',
                    'description': '',
                })

    right = node.child_by_field_name('right')
    if right is not None:
        _extract_calls(right, source, parent_class_id, relations)


def _handle_self_assignment(node, source, parent_class_id, qualifier, entities, relations,
                             line_start, line_end):
    left = node.child_by_field_name('left')
    if left is None:
        return
    if left.type != 'attribute':
        return
    base = left.child_by_field_name('object')
    attr = left.child_by_field_name('attribute')
    if base is None or attr is None:
        return
    base_text = base.text.decode('utf-8')
    attr_text = attr.text.decode('utf-8')
    if base_text not in ('self', 'this'):
        return
    member_id = f"{qualifier}.{attr_text}" if qualifier else attr_text
    entities.append({
        'id': member_id,
        'type': 'variable',
        'name': attr_text,
        'file': '',
        'line_start': line_start,
        'line_end': line_end,
        'description': '',
    })
    relations.append({
        'source_id': parent_class_id,
        'target_id': member_id,
        'type': 'contains',
        'description': '',
    })
    right = node.child_by_field_name('right')
    if right is not None:
        _extract_calls(right, source, parent_class_id, relations)


def _extract_class_member(node, source, parent_class_id, class_qualified_name, entities, relations):
    for child in node.named_children:
        if child.type == 'assignment':
            left = child.child_by_field_name('left')
            if left is not None and left.type == 'attribute':
                base = left.child_by_field_name('object')
                attr = left.child_by_field_name('attribute')
                if base is not None and attr is not None:
                    base_text = base.text.decode('utf-8')
                    attr_text = attr.text.decode('utf-8')
                    if base_text in ('self', 'this'):
                        member_id = f"{class_qualified_name}.{attr_text}"
                        line_start = node.start_point[0] + 1
                        line_end = node.end_point[0] + 1
                        entities.append({
                            'id': member_id,
                            'type': 'variable',
                            'name': attr_text,
                            'file': '',
                            'line_start': line_start,
                            'line_end': line_end,
                            'description': '',
                        })
                        relations.append({
                            'source_id': parent_class_id,
                            'target_id': member_id,
                            'type': 'contains',
                            'description': '',
                        })


def _handle_import_statement(node, source, language, entities, relations):
    if language == 'python':
        module_name_node = node.child_by_field_name('name')
        if module_name_node is None:
            return
        if module_name_node.type == 'dotted_name':
            parts = [c.text.decode('utf-8') for c in module_name_node.named_children]
            module_name = '.'.join(parts)
        else:
            module_name = module_name_node.text.decode('utf-8')

        entities.append({
            'id': module_name,
            'type': 'import',
            'name': module_name,
            'file': '',
            'line_start': node.start_point[0] + 1,
            'line_end': node.end_point[0] + 1,
            'description': '',
        })
    else:
        source_node = node.child_by_field_name('source')
        if source_node is None:
            return
        module_name = source_node.text.decode('utf-8').strip('"').strip("'")
        entities.append({
            'id': module_name,
            'type': 'import',
            'name': module_name,
            'file': '',
            'line_start': node.start_point[0] + 1,
            'line_end': node.end_point[0] + 1,
            'description': '',
        })


def _handle_import_from(node, source, entities, relations):
    module_name_node = node.child_by_field_name('module_name')
    if module_name_node is not None:
        if module_name_node.type == 'dotted_name':
            parts = [c.text.decode('utf-8') for c in module_name_node.named_children]
            module_name = '.'.join(parts)
        else:
            module_name = module_name_node.text.decode('utf-8')

        entities.append({
            'id': module_name,
            'type': 'import',
            'name': module_name,
            'file': '',
            'line_start': node.start_point[0] + 1,
            'line_end': node.end_point[0] + 1,
            'description': '',
        })


def _extract_js_heritage(node, source, class_id, relations):
    heritage = node.child_by_field_name('extends')
    if heritage is not None:
        for sc_node in heritage.named_children:
            sc_name = sc_node.text.decode('utf-8')
            if sc_name:
                relations.append({
                    'source_id': class_id,
                    'target_id': sc_name,
                    'type': 'inherits',
                    'description': '',
                })
    implements = node.child_by_field_name('implements')
    if implements is not None:
        for impl_node in implements.named_children:
            impl_name = impl_node.text.decode('utf-8')
            if impl_name:
                relations.append({
                    'source_id': class_id,
                    'target_id': impl_name,
                    'type': 'inherits',
                    'description': '',
                })


def _extract_calls(node, source: str, caller_id: Optional[str], relations: List[Dict]):
    if caller_id is None:
        return

    call_names = set()

    def find_calls(n):
        if n.type == 'call':
            func_node = n.child_by_field_name('function')
            if func_node is not None:
                if func_node.type == 'identifier':
                    call_name = func_node.text.decode('utf-8')
                    call_names.add(call_name)
                elif func_node.type == 'attribute':
                    attr_node = func_node.child_by_field_name('attribute')
                    if attr_node is not None:
                        call_name = attr_node.text.decode('utf-8')
                        call_names.add(call_name)
                    base = func_node.child_by_field_name('object')
                    if base is not None:
                        find_calls(base)
        for child in n.named_children:
            find_calls(child)

    if node.type == 'call':
        find_calls(node)

    for child in node.named_children:
        find_calls(child)

    for call_name in call_names:
        if call_name:
            relations.append({
                'source_id': caller_id,
                'target_id': call_name,
                'type': 'calls',
                'description': '',
            })