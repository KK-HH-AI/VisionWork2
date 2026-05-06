export function getMonacoLanguage(filename) {
  const ext = filename.split('.').pop().toLowerCase();
  const langMap = {
    'js': 'javascript', 'jsx': 'javascript', 'ts': 'typescript', 'tsx': 'typescript',
    'py': 'python', 'java': 'java', 'cpp': 'cpp', 'c': 'c', 'h': 'c',
    'html': 'html', 'css': 'css', 'scss': 'scss', 'less': 'less',
    'json': 'json', 'xml': 'xml', 'yaml': 'yaml', 'yml': 'yaml',
    'md': 'markdown', 'sql': 'sql', 'sh': 'shell', 'bat': 'shell',
    'go': 'go', 'rs': 'rust', 'swift': 'swift', 'kt': 'kotlin',
    'php': 'php', 'lua': 'lua', 'r': 'r', 'rb': 'ruby',
    'vue': 'html', 'svelte': 'html', 'graphql': 'graphql',
  };
  return langMap[ext] || 'plaintext';
}
