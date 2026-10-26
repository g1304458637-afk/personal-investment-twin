import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { communityApi } from '@/data/communityApi';
import { Share2 } from 'lucide-react';
import type { InvestmentInput } from '@/data/investmentSharing';
import { storeInvestmentPost } from '@/data/communityDemo';
import { InvestmentShareDialog } from './InvestmentShareDialog';

/** Mounted inside an owner-scoped account view; raw account inputs stay in React memory. */
export function InvestmentShareEntry({getInputs}:{getInputs:()=>InvestmentInput[]}) {
  const [open,setOpen]=useState(false),[inputs,setInputs]=useState<InvestmentInput[]>([]),[error,setError]=useState('');
  const navigate=useNavigate();
  const [destination,setDestination]=useState<'local'|'members'>('local');
  const prepare=async(target:'local'|'members')=>{try{if(target==='members')await communityApi('session');setInputs(getInputs());setDestination(target);setError('');setOpen(true);}catch(e){setError(e instanceof Error?e.message:'当前记录还不足以生成分享卡。');}};
  return <section className="cm-account-share-entry">
    <div><strong>把投资经历，变成可讨论的复盘</strong><p>先选择展示范围并预览。账户标识、原始流水与持仓股数不会随卡片分享。</p>{error&&<p role="alert">{error}</p>}</div>
    <button type="button" className="cm-button" onClick={()=>void prepare('local')}><Share2 size={14}/>生成本地分享卡</button>
    <button type="button" className="cm-button" onClick={()=>void prepare('members')}><Share2 size={14}/>分享到多人社区</button>
    {error&&<button className="cm-button" onClick={()=>navigate('/community')}>进入社区登录</button>}
    <InvestmentShareDialog open={open} onOpenChange={setOpen} inputs={inputs} destination={destination} onPublish={async(card,narrative,request_id)=>{
      if(destination==='members'){
        const next=await communityApi<{id:number}>('posts',{card,narrative,request_id});
        navigate(`/community?post=${next.id}`);
      }else{
        const next=storeInvestmentPost(localStorage,card,narrative);
        navigate(`/community-demo?post=${encodeURIComponent(next.posts.at(-1)!.id)}&view=research`);
      }
    }}/>
  </section>;
}
