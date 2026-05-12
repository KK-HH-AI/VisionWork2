import React, { useState, useEffect, useCallback } from 'react';
import { X, Edit2, Save, Code, Plus, Trash2 } from 'react-feather';

interface SkillInfo {
  name: string;
  description: string;
  enabled: boolean;
}

interface SkillManagerProps {
  isOpen: boolean;
  onClose: () => void;
  backendPort: number | null;
}

export default function SkillManager({ isOpen, onClose, backendPort }: SkillManagerProps) {
  const [skills, setSkills] = useState<SkillInfo[]>([]);
  const [editingSkill, setEditingSkill] = useState<string | null>(null);
  const [yamlContent, setYamlContent] = useState('');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newSkillName, setNewSkillName] = useState('');
  const [newSkillDesc, setNewSkillDesc] = useState('');

  const fetchSkills = useCallback(async () => {
    if (!backendPort) return;
    try {
      const res = await fetch(`http://127.0.0.1:${backendPort}/skills`);
      if (res.ok) {
        const data = await res.json();
        setSkills(data);
      }
    } catch (e) {
      console.error('Failed to fetch skills:', e);
    }
  }, [backendPort]);

  useEffect(() => {
    if (isOpen) {
      fetchSkills();
      setEditingSkill(null);
      setYamlContent('');
      setMessage(null);
      setShowCreateForm(false);
      setNewSkillName('');
      setNewSkillDesc('');
    }
  }, [isOpen, fetchSkills]);

  const toggleEnabled = async (skillName: string, currentEnabled: boolean) => {
    if (!backendPort) return;
    try {
      const res = await fetch(`http://127.0.0.1:${backendPort}/skills/${skillName}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: !currentEnabled }),
      });
      if (res.ok) {
        setSkills((prev) =>
          prev.map((s) =>
            s.name === skillName ? { ...s, enabled: !currentEnabled } : s
          )
        );
      }
    } catch (e) {
      console.error('Failed to toggle skill:', e);
    }
  };

  const openYamlEditor = async (skillName: string) => {
    if (!backendPort) return;
    try {
      const res = await fetch(`http://127.0.0.1:${backendPort}/skills/${skillName}/yaml`);
      if (res.ok) {
        const data = await res.json();
        setEditingSkill(skillName);
        setYamlContent(data.yaml);
        setMessage(null);
      }
    } catch (e) {
      console.error('Failed to fetch skill YAML:', e);
    }
  };

  const saveYaml = async () => {
    if (!backendPort || !editingSkill) return;
    setSaving(true);
    try {
      const res = await fetch(`http://127.0.0.1:${backendPort}/skills/${editingSkill}/yaml`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ yaml: yamlContent }),
      });
      if (res.ok) {
        setMessage('YAML saved successfully');
        setEditingSkill(null);
        fetchSkills();
      } else {
        const err = await res.json();
        setMessage(`Failed: ${err.detail || 'Unknown error'}`);
      }
    } catch (e) {
      setMessage(`Failed: ${e}`);
    } finally {
      setSaving(false);
    }
  };

  const createSkill = async () => {
    if (!backendPort) return;
    if (!newSkillName.trim()) {
      setMessage('Skill name is required');
      return;
    }
    setSaving(true);
    try {
      const res = await fetch(`http://127.0.0.1:${backendPort}/skills`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: newSkillName.trim(),
          description: newSkillDesc.trim(),
        }),
      });
      if (res.ok) {
        setMessage('Skill created successfully');
        setShowCreateForm(false);
        setNewSkillName('');
        setNewSkillDesc('');
        fetchSkills();
      } else {
        const err = await res.json();
        setMessage(`Failed: ${err.detail || 'Unknown error'}`);
      }
    } catch (e) {
      setMessage(`Failed: ${e}`);
    } finally {
      setSaving(false);
    }
  };

  const deleteSkill = async (skillName: string) => {
    if (!backendPort) return;
    if (!confirm(`确定要删除 skill "${skillName}" 吗？此操作不可撤销。`)) return;
    try {
      const res = await fetch(`http://127.0.0.1:${backendPort}/skills/${skillName}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        setMessage(`Skill "${skillName}" deleted`);
        fetchSkills();
      } else {
        const err = await res.json();
        setMessage(`Failed: ${err.detail || 'Unknown error'}`);
      }
    } catch (e) {
      setMessage(`Failed: ${e}`);
    }
  };

  if (!isOpen) return null;

    return (
      <div className="skill-manager-overlay" onClick={onClose}>
        <div className="skill-manager-modal" onClick={(e) => e.stopPropagation()}>
          <div className="skill-manager-header">
            <h2>Skill 管理</h2>
            <div className="skill-manager-header-actions">
              {!editingSkill && !showCreateForm && (
                <button
                  className="btn-sm btn-primary"
                  onClick={() => setShowCreateForm(true)}
                  title="新增 Skill"
                >
                  <Plus size={14} />
                  新增
                </button>
              )}
              <button className="btn-icon" onClick={onClose} title="关闭">
                <X size={18} />
              </button>
            </div>
          </div>

          {showCreateForm ? (
            <div className="skill-create-form">
              <div className="skill-create-header">
                <div className="skill-create-title">
                  <Plus size={14} />
                  <span>新增 Skill</span>
                </div>
                <div className="skill-create-actions">
                  <button
                    className="btn-sm"
                    onClick={() => {
                      setShowCreateForm(false);
                      setNewSkillName('');
                      setNewSkillDesc('');
                    }}
                    disabled={saving}
                  >
                    取消
                  </button>
                  <button
                    className="btn-sm btn-primary"
                    onClick={createSkill}
                    disabled={saving}
                  >
                    <Save size={14} />
                    {saving ? '创建中...' : '创建'}
                  </button>
                </div>
              </div>
              <div className="skill-create-fields">
                <div className="skill-field">
                  <label>Skill 名称</label>
                  <input
                    type="text"
                    value={newSkillName}
                    onChange={(e) => setNewSkillName(e.target.value)}
                    placeholder="例如: my_custom_skill"
                    className="skill-field-input"
                  />
                </div>
                <div className="skill-field">
                  <label>描述</label>
                  <input
                    type="text"
                    value={newSkillDesc}
                    onChange={(e) => setNewSkillDesc(e.target.value)}
                    placeholder="简要描述此 Skill 的功能"
                    className="skill-field-input"
                  />
                </div>
              </div>
              {message && <div className="skill-message">{message}</div>}
            </div>
          ) : editingSkill ? (
            <div className="skill-yaml-editor">
              <div className="skill-yaml-header">
                <div className="skill-yaml-title">
                  <Code size={14} />
                  <span>编辑 {editingSkill}.yml</span>
                </div>
                <div className="skill-yaml-actions">
                  <button
                    className="btn-sm"
                    onClick={() => setEditingSkill(null)}
                    disabled={saving}
                  >
                    取消
                  </button>
                  <button
                    className="btn-sm btn-primary"
                    onClick={saveYaml}
                    disabled={saving}
                  >
                    <Save size={14} />
                    {saving ? '保存中...' : '保存'}
                  </button>
                </div>
              </div>
              <textarea
                className="skill-yaml-textarea"
                value={yamlContent}
                onChange={(e) => setYamlContent(e.target.value)}
                spellCheck={false}
              />
              {message && <div className="skill-message">{message}</div>}
            </div>
          ) : (
            <div className="skill-list">
              {skills.length === 0 ? (
                <div className="skill-list-empty">暂无技能，点击"新增"创建</div>
              ) : (
                skills.map((skill) => (
                  <div key={skill.name} className="skill-item">
                    <div className="skill-info">
                      <div className="skill-name">{skill.name}</div>
                      <div className="skill-desc">{skill.description}</div>
                    </div>
                    <div className="skill-actions">
                      <button
                        className={`toggle-switch ${skill.enabled ? 'on' : 'off'}`}
                        onClick={() => toggleEnabled(skill.name, skill.enabled)}
                        title={skill.enabled ? '禁用' : '启用'}
                      >
                        <div className="toggle-knob" />
                      </button>
                      <button
                        className="btn-icon btn-sm-icon"
                        onClick={() => openYamlEditor(skill.name)}
                        title="编辑 YAML"
                      >
                        <Edit2 size={14} />
                      </button>
                      <button
                        className="btn-icon btn-sm-icon btn-danger"
                        onClick={() => deleteSkill(skill.name)}
                        title="删除"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      </div>
    );
  }
