const account={subject_id:'qa-fixture',account_id:'qa-fixture',display_name:'合成验收账户',ledger_enabled:true,initial_cash:10000};
export const useDataMode=()=>({activeAccount:account,runtimeAvailable:true,mode:'real_user',refresh:async()=>{}});
