#!/usr/bin/env node

const { execSync, spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const rootDir = path.resolve(__dirname, '..');

console.log(`
========================================================
  ____             _        ____ _ _           
 |  _ \\ ___  _ __ (_)_ __  / ___| (_)_ __  ___ 
 | |_) / _ \\| '_ \\| | '_ \\| |   | | | '_ \\/ __|
 |  _ < (_) | | | | | | | | |___| | | |_) \\__ \\
 |_| \\_\\___/|_| |_|_|_| |_|\\____|_|_| .__/|___/
                                    |_|        
             LOCAL AI VIDEO CLIPPER
========================================================
`);

function checkCommand(cmd, label) {
  try {
    execSync(`${cmd} --version`, { stdio: 'ignore' });
    console.log(`  ✅ ${label} detected`);
    return true;
  } catch (err) {
    console.log(`  ❌ ${label} not found in PATH!`);
    return false;
  }
}

console.log('Checking environment requirements...');
const php = checkCommand('php', 'PHP 8.2+');
const python = checkCommand('python', 'Python 3.10+');
const composer = checkCommand('composer', 'Composer');
const ffmpeg = checkCommand('ffmpeg', 'FFmpeg');

if (!php || !python) {
  console.error('\n[ERROR] PHP and Python are required to run RoninClips.');
  process.exit(1);
}

// Ensure .env exists
const envPath = path.join(rootDir, '.env');
const envExample = path.join(rootDir, '.env.example');
if (!fs.existsSync(envPath) && fs.existsSync(envExample)) {
  console.log('\n[1/3] Creating .env file...');
  fs.copyFileSync(envExample, envPath);
  try {
    execSync('php artisan key:generate', { cwd: rootDir, stdio: 'inherit' });
  } catch (e) {}
}

// Ensure composer dependencies
if (!fs.existsSync(path.join(rootDir, 'vendor'))) {
  console.log('\n[2/3] Installing PHP dependencies...');
  try {
    execSync('composer install --no-interaction', { cwd: rootDir, stdio: 'inherit' });
  } catch (e) {}
}

// Ensure SQLite database file exists if needed
const dbDir = path.join(rootDir, 'database');
const sqlitePath = path.join(dbDir, 'database.sqlite');
if (!fs.existsSync(dbDir)) {
  fs.mkdirSync(dbDir, { recursive: true });
}
if (!fs.existsSync(sqlitePath)) {
  fs.writeFileSync(sqlitePath, '');
}

// Ensure database migration & storage symlink
console.log('\n[3/3] Running database migrations and linking storage...');
try {
  execSync('php artisan migrate --force', { cwd: rootDir, stdio: 'inherit' });
  execSync('php artisan storage:link', { cwd: rootDir, stdio: 'ignore' });
} catch (e) {}

console.log('\n========================================================');
console.log('  🚀 Launching RoninClips Dashboard at http://127.0.0.1:8000');
console.log('========================================================\n');

// Open browser
const openCmd = process.platform === 'win32' ? 'start' : process.platform === 'darwin' ? 'open' : 'xdg-open';
try {
  execSync(`${openCmd} http://127.0.0.1:8000`, { stdio: 'ignore' });
} catch (e) {}

// Spawn php artisan serve
const server = spawn('php', ['artisan', 'serve', '--port=8000'], { cwd: rootDir, stdio: 'inherit' });
