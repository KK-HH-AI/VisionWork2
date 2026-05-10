import React from 'react';
import { FileText, Code, Image, Table, File } from 'react-feather';

const CODE_EXTS = new Set(['js', 'jsx', 'ts', 'tsx', 'py', 'java', 'cpp', 'c', 'h', 'html', 'css', 'scss', 'less', 'json', 'xml', 'yaml', 'yml', 'md']);
const IMAGE_EXTS = new Set(['png', 'jpg', 'jpeg', 'gif', 'svg', 'ico', 'webp']);
const TABLE_EXTS = new Set(['csv', 'xlsx', 'xls']);

export function getFileIcon(filename: string): React.ReactNode {
  const ext = filename.split('.').pop()?.toLowerCase() || '';
  if (CODE_EXTS.has(ext)) return React.createElement(Code, { size: 14 });
  if (IMAGE_EXTS.has(ext)) return React.createElement(Image, { size: 14 });
  if (TABLE_EXTS.has(ext)) return React.createElement(Table, { size: 14 });
  return React.createElement(FileText, { size: 14 });
}