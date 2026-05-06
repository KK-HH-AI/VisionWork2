import os

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.dirname(BACKEND_DIR)
PROJECT_ROOT = os.path.dirname(SRC_DIR)
WORKSPACE_ROOT = os.path.join(PROJECT_ROOT, 'workspace')

TEXT_EXTENSIONS = {
    '.py', '.js', '.jsx', '.ts', '.tsx', '.java', '.cpp', '.c', '.h', '.hpp',
    '.html', '.css', '.scss', '.less', '.json', '.yaml', '.yml', '.xml',
    '.md', '.txt', '.csv', '.sh', '.bat', '.ps1', '.sql', '.r', '.rb',
    '.go', '.rs', '.swift', '.kt', '.scala', '.php', '.lua', '.pl',
    '.toml', '.ini', '.cfg', '.env', '.gitignore', '.dockerfile',
    '.vue', '.svelte', '.astro', '.graphql', '.proto',
}

BINARY_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.bmp', '.webp',
    '.mp3', '.wav', '.mp4', '.avi', '.mov', '.webm',
    '.zip', '.tar', '.gz', '.rar', '.7z',
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.exe', '.dll', '.so', '.dylib', '.bin',
    '.ttf', '.otf', '.woff', '.woff2', '.eot',
    '.pyc', '.pyo', '.class', '.o', '.obj',
}

MAX_FILE_SIZE = 200 * 1024

IGNORE_DIRS = {
    'node_modules', '.git', '__pycache__', 'dist', 'dist-electron',
    '.venv', 'venv', 'workspace', '.vite', 'build', 'target',
    '.next', '.nuxt', 'coverage', '.tox', '.eggs',
}

IGNORE_FILE_PATTERNS = {
    'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml',
    'poetry.lock', 'Pipfile.lock',
}
