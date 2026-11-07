export function replayBounds(dates:string[],range?:{start:string;end:string}){
  if(!dates.length)throw new Error('回放没有交易日期。');
  if(!range)return {start:0,end:dates.length-1};
  if(range.start>range.end)throw new Error('回放的开始日期晚于结束日期。');
  const start=dates.findIndex(date=>date>=range.start&&date<=range.end);
  let end=dates.length-1;
  while(end>=0&&dates[end]>range.end)end--;
  if(start<0||end<start)throw new Error('这段日期没有可回放的交易日。');
  return {start,end};
}
