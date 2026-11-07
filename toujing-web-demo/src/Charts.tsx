import {useEffect,useLayoutEffect,useId,useMemo,useRef,useState} from 'react';
import {Bar,COLORS,DemoData,Fill,Path,linePath,money} from './model';

function usePlotSize(){const ref=useRef<HTMLDivElement>(null);const [size,setSize]=useState({width:1000,height:300});useLayoutEffect(()=>{const el=ref.current;if(!el)return;const measure=()=>{const b=el.getBoundingClientRect();if(b.width>0&&b.height>0)setSize(old=>old.width===b.width&&old.height===b.height?old:{width:b.width,height:b.height});};const o=new ResizeObserver(measure);o.observe(el);measure();return()=>o.disconnect();},[]);return {ref,...size};}

export function CareerLine({data,onPick}:{data:DemoData;onPick?:(index:number)=>void}){
 const gradient=useId();const days=data.paths[0].days;const [hover,setHover]=useState<number|null>(null);const values=days.map(d=>Number(d.equity)/10000),flows=days.map(d=>50+Number(d.net_contributions)/10000);
 const lo=Math.floor(Math.min(...values,...flows)/10)*10,hi=Math.ceil(Math.max(...values,...flows)/10)*10,w=1000,h=200;const active=hover==null?days.length-1:hover;
 return <div className="career-plot" onMouseLeave={()=>setHover(null)}><svg viewBox="0 0 1080 250" role="img" aria-label="2020年至2025年账户资产与累计净投入趋势">
  <defs><linearGradient id={gradient} x1="0" y1="0" x2="0" y2="1"><stop stopColor="#91d1f9" stopOpacity=".2"/><stop offset="1" stopColor="#91d1f9" stopOpacity="0"/></linearGradient></defs>
  <g transform="translate(42 12)">{Array.from({length:6},(_,i)=>lo+(hi-lo)*i/5).map(v=><g key={v}><line x2={w} y1={h-(v-lo)/(hi-lo)*h} y2={h-(v-lo)/(hi-lo)*h} className="gridline"/><text x="-12" y={h-(v-lo)/(hi-lo)*h+4} textAnchor="end" className="axis-label">{v.toFixed(0)}万</text></g>)}
  <path d={linePath(values,w,h,lo,hi)+` L${w},${h} L0,${h}Z`} fill={`url(#${gradient})`}/>
  <path d={linePath(flows,w,h,lo,hi)} fill="none" stroke="#e8ac7e" strokeWidth="1.8" strokeDasharray="7 5"/>
  <path d={linePath(values,w,h,lo,hi)} fill="none" stroke="#b6e2ff" strokeWidth="2.2" vectorEffect="non-scaling-stroke"/>
  {data.lifetime.years.map((y,i)=><text key={y.year} x={i*w/5} y={h+26} textAnchor={i===0?'start':i===5?'end':'middle'} className="axis-label">{y.year}</text>)}
  {hover!==null&&<><line x1={active/(days.length-1)*w} x2={active/(days.length-1)*w} y2={h} stroke="#9fddff" strokeDasharray="3 3"/><circle cx={active/(days.length-1)*w} cy={h-(values[active]-lo)/(hi-lo)*h} r="4" fill="#d6f0ff"/></>}
  <rect width={w} height={h} fill="transparent" onMouseMove={e=>{const b=e.currentTarget.getBoundingClientRect();setHover(Math.max(0,Math.min(days.length-1,Math.round((e.clientX-b.left)/b.width*(days.length-1)))));}} onClick={()=>onPick?.(active)}/>
  </g></svg>{hover!==null&&<div className="chart-hover">{days[active].date} · 资产 ¥{money(days[active].equity)}</div>}</div>;
}

const PLOT_LEFT=8;
const PLOT_MARGIN=72;
const SERIES_DASH=[undefined,'8 3',undefined,'3 3','10 3 3 3','5 4'];

const slotCenter=(index:number,count:number,width:number)=>(index+.5)*width/count;
const slotAt=(clientX:number,element:SVGRectElement,count:number)=>{
 const rect=element.getBoundingClientRect();
 return Math.max(0,Math.min(count-1,Math.floor((clientX-rect.left)/rect.width*count)));
};

function DateAxis({dates,width,y}:{dates:string[];width:number;y:number}){
 const last=dates.length-1;
 const count=Math.max(2,Math.min(6,Math.floor(width/105)));
 const indexes=Array.from(new Set(Array.from({length:count},(_,i)=>Math.round(i*last/(count-1)))));
 return <g aria-hidden="true">{indexes.map(index=><text key={index} x={slotCenter(index,dates.length,width)} y={y}
  textAnchor={last===0?'middle':index===0?'start':index===last?'end':'middle'} className="nav-axis-label">
  {dates[index].slice(0,dates.length>260?7:10)}
 </text>)}</g>;
}

function Playhead({x,height,date}:{x:number;height:number;date:string}){
 return <line data-replay-playhead={date} x1={x} x2={x} y2={height}
  stroke="#d4eaff" strokeOpacity=".76" strokeWidth="1.2" pointerEvents="none"/>;
}

export function ReplayChart({paths,dates,startIndex,cursor,selected,onSeek,metric='nav'}:{
 paths:Path[];dates:string[];startIndex:number;cursor:number;selected:number[];
 onSeek:(n:number)=>void;metric?:'nav'|'equity'|'drawdown';
}){
 const [hover,setHover]=useState<number|null>(null);
 const size=usePlotSize();
 const reveal=useId();
 const width=Math.max(1,size.width-PLOT_MARGIN);
 const showDates=size.height>=94;
 const height=Math.max(18,size.height-(showDates?24:10));
 const len=dates.length;

 // The window defines the geometry. Advancing the cursor only reveals it.
 const geometry=useMemo(()=>{
  const values=paths.map(path=>path.days.slice(startIndex,startIndex+len).map(day=>
   metric==='equity'?Number(day.equity)/10000:metric==='drawdown'?Number(day.drawdown)*100:Number(day.nav)));
  const all=values.flat();
  const bottom=Math.min(...all);
  const top=Math.max(...all);
  const padding=Math.max(metric==='nav'?.015:.4,(top-bottom)*.12);
  const min=bottom-padding;
  const max=metric==='drawdown'?0:top+padding;
  const span=width*(len-1)/len;
  return {values,min,max,paths:values.map(series=>linePath(series,span,height,min,max))};
 },[paths,startIndex,len,metric,width,height]);
 const y=(value:number)=>height-(value-geometry.min)/(geometry.max-geometry.min)*height;
 const x=(index:number)=>slotCenter(index,len,width);
 const format=(value:number)=>metric==='equity'?`${value.toFixed(1)}万`:metric==='drawdown'?`${value.toFixed(1)}%`:value.toFixed(3);
 const tickFractions=height>=52?[0,.5,1]:height>=30?[0,1]:[.5];
 const ticks=tickFractions.map(n=>geometry.min+(geometry.max-geometry.min)*n);
 const hoverDate=hover===null?undefined:dates[hover];
 return <div className="replay-plot" ref={size.ref}>
  <svg viewBox={`0 0 ${size.width} ${size.height}`} role="img" aria-label="六条组合路径，共用固定日期轴"
   onPointerLeave={()=>setHover(null)}>
   <defs><clipPath id={reveal}><rect x="-3" y="-3" width={x(cursor)+3} height={height+6}/></clipPath></defs>
   <g transform={`translate(${PLOT_LEFT} 5)`}>
    {ticks.map(value=><g key={value}><line x2={width} y1={y(value)} y2={y(value)} className="gridline"/>
     <text x={width+8} y={Math.max(9,y(value)+3)} className="nav-axis-label">{format(value)}</text></g>)}
    {showDates&&<DateAxis dates={dates} width={width} y={height+16}/>}
    <g clipPath={`url(#${reveal})`}>
     {selected.map(i=><path key={i} data-path={i} d={geometry.paths[i]} transform={`translate(${width/(2*len)} 0)`}
      fill="none" stroke={COLORS[i]} strokeWidth={i===0?2.6:2} strokeDasharray={SERIES_DASH[i]}
      strokeLinejoin="round" vectorEffect="non-scaling-stroke"/>)}
    </g>
    <Playhead x={x(cursor)} height={height} date={dates[cursor]}/>
    {selected.map(i=><circle key={i} cx={x(cursor)} cy={y(geometry.values[i][cursor])}
     r={i===0?3.5:2.8} fill={COLORS[i]} stroke="#0c1826" strokeWidth="1"/>)}
    {hoverDate&&<line x1={x(hover!)} x2={x(hover!)} y2={height} stroke="#acd0e8" strokeOpacity=".65" strokeDasharray="3 4"/>}
    <rect width={width} height={height} fill="transparent" style={{cursor:'pointer'}}
     onPointerMove={event=>setHover(slotAt(event.clientX,event.currentTarget,len))}
     onClick={event=>onSeek(startIndex+slotAt(event.clientX,event.currentTarget,len))}/>
   </g>
  </svg>
  {hoverDate&&<span className="plot-date">{hoverDate} · 点击定位</span>}
 </div>;
}

type MarketMarker=Fill&{pathIndex:number;pathName:string;label?:string};
type PriceChartProps={
 bars:Bar[];dates:string[];cursor:number;fills:MarketMarker[];unit:string;
 onPick:(date:string)=>void;onRange:(start:string,end:string)=>void;onSelectionStart:()=>void;
 selection?:[string,string];selecting:boolean;
 mode?:'static'|'replay';onHoverDateChange?:(date:string|null)=>void;
 onMarkerPick?:(fill:Fill)=>void;
};

export function PriceChart({bars,dates,cursor,fills,unit,onPick,onRange,onSelectionStart,selection,selecting,mode='replay',onHoverDateChange,onMarkerPick}:PriceChartProps){
 const [hover,setHover]=useState<number|null>(null);
 const [drag,setDrag]=useState<[number,number]|null>(null);
 const anchor=useRef<number|null>(null);
 const size=usePlotSize();
 const reveal=useId();
 const width=Math.max(1,size.width-PLOT_MARGIN);
 const height=Math.max(38,size.height-38);
 const step=width/dates.length;
 const x=(index:number)=>slotCenter(index,dates.length,width);
 const byDate=useMemo(()=>new Map(bars.map(bar=>[bar.date,bar])),[bars]);
 const geometry=useMemo(()=>{
  // Keep an empty slot for a missing candle, so trades and both playheads
  // still align with the portfolio calendar.
  const windowBars=dates.flatMap((date,index)=>{
   const bar=byDate.get(date);
   return bar?[{bar,index}]:[];
  });
  if(!windowBars.length)return null;
  const min=Math.min(...windowBars.map(({bar})=>Number(bar.low)))*.985;
  const max=Math.max(...windowBars.map(({bar})=>Number(bar.high)))*1.015;
  const y=(price:number)=>height-(price-min)/(max-min)*height;
  const shapes=[{wick:'',body:''},{wick:'',body:''}];
  const bodyWidth=Math.min(16,step*.64);
  for(const {bar,index} of windowBars){
   const open=y(Number(bar.open));
   const close=y(Number(bar.close));
   const center=slotCenter(index,dates.length,width);
   const group=shapes[close<=open?0:1];
   group.wick+=`M${center.toFixed(2)},${y(Number(bar.high)).toFixed(2)}V${y(Number(bar.low)).toFixed(2)}`;
   group.body+=`M${(center-bodyWidth/2).toFixed(2)},${Math.min(open,close).toFixed(2)}h${bodyWidth.toFixed(2)}v${Math.max(.8,Math.abs(close-open)).toFixed(2)}h-${bodyWidth.toFixed(2)}Z`;
  }
  return {min,max,shapes};
 },[byDate,dates,height,width,step]);
 const dateIndex=useMemo(()=>new Map(dates.map((date,index)=>[date,index])),[dates]);
 const tradesByDate=useMemo(()=>{
  const result=new Map<string,MarketMarker[]>();
  for(const fill of fills){
   const row=result.get(fill.date)??[];
   row.push(fill);
   result.set(fill.date,row);
  }
  return result;
 },[fills]);
 useEffect(()=>{onHoverDateChange?.(hover===null?null:dates[hover]??null);},[hover,dates,onHoverDateChange]);

 if(!geometry)return <div className="price-plot empty-inline" ref={size.ref}>这段日期没有本地行情</div>;
 const y=(price:number)=>height-(price-geometry.min)/(geometry.max-geometry.min)*height;
 const current=dates[cursor];
 const hoverDate=hover!==null&&hover<=cursor?dates[hover]:undefined;
 const hoverBar=hoverDate?byDate.get(hoverDate):undefined;
 const hoverFills=hoverDate?tradesByDate.get(hoverDate)??[]:[];
 const selected=drag??(selection?[dateIndex.get(selection[0])??-1,dateIndex.get(selection[1])??-1]:null);
 const tickCount=Math.max(2,Math.min(6,Math.floor(height/60)+1));
 return <div className={`price-plot large ${selecting?'is-selecting':''}`} ref={size.ref}
  onPointerLeave={()=>{if(anchor.current===null)setHover(null);}}>
  <svg viewBox={`0 0 ${size.width} ${size.height}`} role={mode==='static'?'group':'img'} aria-label={mode==='static'?'本轮投资的历史日K线与本人买卖标记':'未复权历史日K线和六路径教学成交'}>
   <defs><clipPath id={reveal}><rect width={(cursor+1)*step} height={height}/></clipPath></defs>
   <g transform={`translate(${PLOT_LEFT} 8)`}>
    {Array.from({length:tickCount},(_,i)=>i/(tickCount-1)).map(fraction=><g key={fraction}>
     <line x2={width} y1={height*fraction} y2={height*fraction} className="gridline"/>
     <text x={width+9} y={height*fraction+4} className="axis-label">{(geometry.max-(geometry.max-geometry.min)*fraction).toFixed(2)}</text>
    </g>)}
    {selected&&Math.min(...selected)>=0&&Math.max(...selected)<=cursor&&<rect
     x={Math.min(...selected)*step} width={(Math.abs(selected[1]-selected[0])+1)*step} height={height}
     fill="#8cd5f7" fillOpacity=".13" stroke="#8cd5f7"/>}
    <g clipPath={`url(#${reveal})`}>
     {geometry.shapes.map((shape,index)=><g key={index} fill={index===0?'#f1a29c':'#80d5c1'}>
      <path d={shape.wick} stroke="currentColor" style={{color:index===0?'#f1a29c':'#80d5c1'}} strokeWidth={Math.min(1,step*.75)} fill="none"/>
      <path data-candle-body={index} d={shape.body}/>
     </g>)}
    </g>
    {mode==='replay'&&<Playhead x={x(cursor)} height={height} date={current}/>}
    <DateAxis dates={dates} width={width} y={height+22}/>
    <rect width={width} height={height} fill="transparent" style={{cursor:selecting?'crosshair':'pointer',touchAction:'none'}}
     onPointerDown={event=>{
      const index=slotAt(event.clientX,event.currentTarget,dates.length);
      if(event.button!==0||index>cursor)return;
      onSelectionStart();
      anchor.current=index;
      setHover(index);
      setDrag([index,index]);
      event.currentTarget.setPointerCapture(event.pointerId);
     }}
     onPointerMove={event=>{
      const index=slotAt(event.clientX,event.currentTarget,dates.length);
      setHover(index<=cursor?index:null);
      if(anchor.current!==null)setDrag([anchor.current,Math.min(index,cursor)]);
     }}
     onPointerCancel={()=>{anchor.current=null;setDrag(null);}}
     onPointerUp={event=>{
      const start=anchor.current;
      if(start===null)return;
      const end=Math.min(cursor,slotAt(event.clientX,event.currentTarget,dates.length));
      anchor.current=null;
      setDrag(null);
      if(event.currentTarget.hasPointerCapture(event.pointerId))event.currentTarget.releasePointerCapture(event.pointerId);
      if(start!==end||selecting)onRange(dates[Math.min(start,end)],dates[Math.max(start,end)]);
      else if(byDate.has(dates[end]))onPick(dates[end]);
     }}/>
    {hoverDate&&<line pointerEvents="none" x1={x(hover!)} x2={x(hover!)} y2={height} stroke="#c0e0f4" strokeDasharray="3 3"/>}
    {fills.map(fill=>{
     const index=dateIndex.get(fill.date);
     if(index===undefined||index>cursor||!byDate.has(fill.date))return null;
     const px=x(index),py=y(Number(fill.price)),buy=fill.side==='BUY';
     const labelY=Math.min(height-24,Math.max(4,py+(buy?13:-33)));
     const labelX=Math.max(0,Math.min(width-36,px-18));
     return <g className="trade-marker" key={fill.pathIndex+'-'+fill.execution_id}
      role={onMarkerPick?'button':undefined} tabIndex={onMarkerPick?0:undefined}
      aria-label={onMarkerPick?`${fill.date} ${fill.label??(buy?'买入':'卖出')} ${fill.quantity}${unit}，查看成交详情`:undefined}
      style={{cursor:onMarkerPick?'pointer':undefined,pointerEvents:onMarkerPick?'auto':'none'}}
      onClick={onMarkerPick?()=>onMarkerPick(fill):undefined}
      onKeyDown={onMarkerPick?event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();onMarkerPick(fill);}}:undefined}
      onPointerEnter={()=>setHover(index)}>
      <polygon transform={`translate(${px} ${py})`} points={buy?'0,-5 4,3 -4,3':'0,5 4,-3 -4,-3'} fill={COLORS[fill.pathIndex]} stroke="#0c1826"/>
      {mode==='static'&&<><line x1={px} x2={px} y1={py} y2={buy?labelY:labelY+22} stroke="#aed7ec" opacity=".55"/>
       <rect x={labelX} y={labelY} width="36" height="22" rx="5" fill="#244559" stroke="#90c4dd66"/>
       <text x={labelX+18} y={labelY+15} textAnchor="middle" fill="#dbf1fa" fontSize="11">{fill.label??(buy?'买入':'卖出')}</text></>}
      {mode==='replay'&&index===cursor&&<circle cx={px} cy={py} r="8" fill="none" stroke={COLORS[fill.pathIndex]}/>}
     </g>;
    })}
   </g>
  </svg>
  {hoverDate&&<div className="candle-tooltip">
   <div>{hoverDate} {hoverBar?`　开 ${hoverBar.open}　高 ${hoverBar.high}　低 ${hoverBar.low}　收 ${hoverBar.close}`:'　当日无本地日线'}</div>
   {hoverFills.map(fill=><div key={fill.pathIndex+'-'+fill.execution_id} className="tooltip-execution">
    <i className="dot" style={{background:COLORS[fill.pathIndex]}}/>{fill.pathName} · {fill.side==='BUY'?'买入':'卖出'} {fill.quantity}{unit} · ¥{fill.price}
   </div>)}
  </div>}
 </div>;
}
