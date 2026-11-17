import {defineConfig} from '@playwright/test';
import fs from 'node:fs';
const macChrome='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
export default defineConfig({testDir:'./tests',testMatch:'*.spec.ts',fullyParallel:false,workers:1,timeout:30000,use:{baseURL:process.env.DIRA_TEST_URL || 'http://127.0.0.1:8000',viewport:{width:1440,height:1000},headless:true,launchOptions:fs.existsSync(macChrome)?{executablePath:macChrome}:{}},reporter:'list'});
