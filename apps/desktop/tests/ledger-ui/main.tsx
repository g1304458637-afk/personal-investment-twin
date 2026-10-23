import {createRoot} from 'react-dom/client';
import {BrowserRouter, Routes, Route} from 'react-router-dom';
import {LedgerWorkspace} from '../../src/components/ledger/LedgerWorkspace';
import {AgentWorkspace} from '../../src/workspace/AgentWorkspace';
import {LocaleProvider} from '../../src/locales/LocaleProvider';
import '../../src/index.css';
createRoot(document.getElementById('root')!).render(<LocaleProvider><BrowserRouter><p style={{background:'#7b521e',padding:12}}>SYNTHETIC QA ONLY · 独立临时数据库 · 浏览器桥接验收，不是用户账户或原生Tauri IPC</p><Routes><Route path="/ask" element={<AgentWorkspace/>}/><Route path="*" element={<LedgerWorkspace/>}/></Routes></BrowserRouter></LocaleProvider>);
