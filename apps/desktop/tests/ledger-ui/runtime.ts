export const isTauriRuntime=()=>true;
export async function runtimeRequest<T>(method:string,params:Record<string,unknown>):Promise<T> {const response=await fetch('http://127.0.0.1:1449/rpc',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({method,params})});const value=await response.json();if(!value.ok)throw new Error(value.error);return value.result;}
export async function pickCsv(){const files=await runtimeRequest<{bars:string}>('qa.files',{});return {path:files.bars,filename:'SYNTHETIC-QA-OHLCV.csv'};}
