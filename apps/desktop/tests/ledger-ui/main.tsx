import {createRoot} from 'react-dom/client';
import {BrowserRouter} from 'react-router-dom';
import {LedgerWorkspace} from '../../src/components/ledger/LedgerWorkspace';
import '../../src/index.css';
createRoot(document.getElementById('root')!).render(<BrowserRouter><p style={{background:'#7b521e',padding:12}}>SYNTHETIC QA ONLY · 独立临时数据库 · 浏览器桥接验收，不是用户账户或原生Tauri IPC</p><LedgerWorkspace/></BrowserRouter>);
