import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';
const root=import.meta.dirname;
export default defineConfig({root,plugins:[{name:'fixture-only-runtime',enforce:'pre',resolveId(source){if(source.endsWith('/DataModeProvider'))return path.join(root,'context.tsx');if(source.endsWith('/runtimeService')||source==='./runtimeService')return path.join(root,'runtime.ts');if(source==='@tauri-apps/plugin-dialog')return path.join(root,'dialog.ts');}},react()],resolve:{alias:{'@':path.resolve(root,'../../src')}},server:{host:'127.0.0.1',port:1448,strictPort:true,fs:{allow:[path.resolve(root,'../..')]}}});
