import React from 'react';
import {createRoot} from 'react-dom/client';
import App from './App';
import './index.css';
import './alignment.css';
class DemoBoundary extends React.Component<{children:React.ReactNode},{error:string}>{
 state={error:''};
 static getDerivedStateFromError(error:Error){return {error:error.message};}
 render(){if(this.state.error)return <div className="boot"><h1>演示画面需要重新载入</h1><p>本地记忆与保存的策略仍然保留。</p><button className="primary" onClick={()=>location.reload()}>重新打开投镜</button><details><summary>查看诊断</summary><p>{this.state.error}</p></details></div>;return this.props.children;}
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><DemoBoundary><App/></DemoBoundary></React.StrictMode>);
