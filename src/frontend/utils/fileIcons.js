const FILE_ICONS = {
  'js': '📜', 'jsx': '⚛️', 'ts': '📘', 'tsx': '⚛️',
  'py': '🐍', 'java': '☕', 'cpp': '⚙️', 'c': '⚙️', 'h': '⚙️',
  'html': '🌐', 'css': '🎨', 'scss': '🎨', 'less': '🎨',
  'json': '📋', 'xml': '📋', 'yaml': '📋', 'yml': '📋',
  'md': '📝', 'txt': '📄', 'csv': '📊',
  'png': '🖼️', 'jpg': '🖼️', 'jpeg': '🖼️', 'gif': '🖼️', 'svg': '🖼️',
  'default': '📄'
};

export function getFileIcon(filename) {
  const ext = filename.split('.').pop().toLowerCase();
  return FILE_ICONS[ext] || FILE_ICONS['default'];
}
