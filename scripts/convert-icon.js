const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const SOURCE_ICON = path.join(__dirname, '..', 'logo.png');
const BUILD_DIR = path.join(__dirname, '..', 'build');
const PUBLIC_DIR = path.join(__dirname, '..', 'src', 'frontend', 'public');

const colors = {
  reset: '\x1b[0m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  red: '\x1b[31m',
  cyan: '\x1b[36m',
};

function log(msg, color = 'reset') {
  console.log(`${colors[color]}${msg}${colors.reset}`);
}

function ensureDir(dirPath) {
  if (!fs.existsSync(dirPath)) {
    fs.mkdirSync(dirPath, { recursive: true });
    log(`✓ 创建目录: ${dirPath}`, 'cyan');
  }
}

if (!fs.existsSync(SOURCE_ICON)) {
  log(`✗ 错误: 找不到源图标文件 ${SOURCE_ICON}`, 'red');
  process.exit(1);
}

log('\n VisionWork2 图标转换工具', 'cyan');
log('═'.repeat(50), 'cyan');

log('\n📦 检查依赖...', 'yellow');
try {
  require.resolve('sharp');
  log('✓ sharp 已安装', 'green');
} catch (e) {
  log('  正在安装 sharp...', 'yellow');
  try {
    execSync('npm install --save-dev sharp', { stdio: 'inherit', cwd: path.join(__dirname, '..') });
    log('✓ sharp 安装成功', 'green');
  } catch (err) {
    log('✗ sharp 安装失败，请手动运行: npm install --save-dev sharp', 'red');
    process.exit(1);
  }
}

const sharp = require('sharp');

log('\n📁 创建目录...', 'yellow');
ensureDir(BUILD_DIR);
ensureDir(PUBLIC_DIR);

async function convertIcons() {
  log('\n🔄 开始转换图标...', 'yellow');
  log('─'.repeat(50), 'cyan');

  const metadata = await sharp(SOURCE_ICON).metadata();
  log(` 源图标尺寸: ${metadata.width}x${metadata.height}`, 'blue');

  log('\n🪟 生成 Windows ICO...', 'yellow');
  await sharp(SOURCE_ICON)
    .resize(256, 256, { fit: 'inside' })
    .toFormat('png')
    .toFile(path.join(BUILD_DIR, 'icon.ico'));
  log('✓ build/icon.ico (256x256)', 'green');

  log('\n🍎 生成 macOS ICNS...', 'yellow');
  
  const iconsetDir = path.join(BUILD_DIR, 'icon.iconset');
  ensureDir(iconsetDir);
  
  const icnsSizes = [
    { name: 'icon_16x16.png', size: 16 },
    { name: 'icon_16x16@2x.png', size: 32 },
    { name: 'icon_32x32.png', size: 32 },
    { name: 'icon_32x32@2x.png', size: 64 },
    { name: 'icon_128x128.png', size: 128 },
    { name: 'icon_128x128@2x.png', size: 256 },
    { name: 'icon_256x256.png', size: 256 },
    { name: 'icon_256x256@2x.png', size: 512 },
    { name: 'icon_512x512.png', size: 512 },
    { name: 'icon_512x512@2x.png', size: 1024 },
  ];

  for (const { name, size } of icnsSizes) {
    await sharp(SOURCE_ICON)
      .resize(size, size, { fit: 'inside' })
      .png()
      .toFile(path.join(iconsetDir, name));
  }
  log('✓ 生成 iconset 目录', 'green');

  if (process.platform === 'darwin') {
    try {
      execSync(`iconutil -c icns "${iconsetDir}" -o "${path.join(BUILD_DIR, 'icon.icns')}"`);
      log('✓ build/icon.icns', 'green');
    } catch (e) {
      log('  iconutil 转换失败', 'yellow');
    }
  } else {
    log('⚠  非 macOS 系统，生成占位 ICNS 文件', 'yellow');
    await sharp(SOURCE_ICON)
      .resize(512, 512, { fit: 'inside' })
      .png()
      .toFile(path.join(BUILD_DIR, 'icon.icns'));
    log('✓ build/icon.icns (占位文件)', 'green');
  }

  fs.rmSync(iconsetDir, { recursive: true, force: true });

  log('\n🐧 生成 Linux PNG...', 'yellow');
  await sharp(SOURCE_ICON)
    .resize(512, 512, { fit: 'inside' })
    .png()
    .toFile(path.join(BUILD_DIR, 'icon.png'));
  log('✓ build/icon.png (512x512)', 'green');

  log('\n🌐 生成 Favicon...', 'yellow');
  await sharp(SOURCE_ICON)
    .resize(32, 32, { fit: 'inside' })
    .png()
    .toFile(path.join(PUBLIC_DIR, 'favicon.png'));
  log('✓ src/frontend/public/favicon.png (32x32)', 'green');

  log('\n📝 更新 package.json...', 'yellow');
  const packageJsonPath = path.join(__dirname, '..', 'package.json');
  const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, 'utf-8'));
  
  packageJson.build.win.icon = 'build/icon.ico';
  packageJson.build.mac.icon = 'build/icon.icns';
  packageJson.build.linux.icon = 'build/icon.png';
  
  fs.writeFileSync(packageJsonPath, JSON.stringify(packageJson, null, 2) + '\n', 'utf-8');
  log('✓ package.json 已更新', 'green');

  log('\n 更新 index.html...', 'yellow');
  const indexPath = path.join(__dirname, '..', 'src', 'frontend', 'index.html');
  let indexHtml = fs.readFileSync(indexPath, 'utf-8');
  
  if (!indexHtml.includes('favicon')) {
    indexHtml = indexHtml.replace(
      '<title>VisionWork2</title>',
      '<title>VisionWork2</title>\n  <link rel="icon" type="image/png" href="/favicon.png">'
    );
    fs.writeFileSync(indexPath, indexHtml, 'utf-8');
    log('✓ index.html 已更新', 'green');
  } else {
    log('✓ index.html 已包含 favicon', 'green');
  }

  log('\n' + '═'.repeat(50), 'cyan');
  log('✅ 图标转换完成！', 'green');
  log('\n📂 生成的文件:', 'cyan');
  log(`  • ${path.join(BUILD_DIR, 'icon.ico')}`, 'blue');
  log(`  • ${path.join(BUILD_DIR, 'icon.icns')}`, 'blue');
  log(`  • ${path.join(BUILD_DIR, 'icon.png')}`, 'blue');
  log(`  • ${path.join(PUBLIC_DIR, 'favicon.png')}`, 'blue');
  log('\n🚀 现在可以运行打包命令:', 'yellow');
  log('  npm run build:win    (Windows)', 'blue');
  log('  npm run build:mac    (macOS)', 'blue');
  log('  npm run dev          (开发模式)', 'blue');
  log('');
}

convertIcons().catch(err => {
  log(`\n✗ 错误: ${err.message}`, 'red');
  console.error(err);
  process.exit(1);
});