import {runtimeRequest} from './runtime';
export async function save(){return (await runtimeRequest<{backup:string}>('qa.files',{})).backup;}
export async function open(){return (await runtimeRequest<{backup:string}>('qa.files',{})).backup;}
