import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import runtimePlugin from './integration/runtimePlugin.ts';
export default defineConfig({
  plugins:[react(),runtimePlugin()],
  server:{
    host:'127.0.0.1',port:18042,strictPort:true,cors:false,
    fs:{deny:['.env','.env.*','*.{crt,pem}','**/.git/**','**/.local/**']}
  },
  build:{outDir:'dist',sourcemap:false}
});
