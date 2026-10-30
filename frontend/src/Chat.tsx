import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Bot, ChevronRight, LoaderCircle, MessageCircle, Send, ShieldCheck } from 'lucide-react';
import { Link } from 'react-router';
import { api, ApiError, savedDraft, saveDraft } from './api/client';
import type { BrowserSessionResponse, ChatHistoryResponse, MessageResponse } from './api/schema';
import { SESSION_KEY, useSession } from './session';
import { ErrorNotice, Loading, PageHeading } from './components';

type Language = 'en' | 'hi' | 'te';
type Operation = { text: string; language: Language; key: string };

export function Chat() {
  const { session } = useSession();
  const sid=session!.session_id;
  const cache=useQueryClient();
  const storage=`chat:${sid}`;
  const [text,setText]=useState(() => savedDraft(`${storage}:text`,''));
  const [language,setLanguage]=useState<Language>('en');
  const [queued,setQueued]=useState<Operation | null>(() => {
    try { const value=JSON.parse(savedDraft(`${storage}:operation`,'null')); return value && typeof value.text==='string' && typeof value.key==='string' && ['en','hi','te'].includes(value.language) ? value : null; } catch { return null; }
  });
  const [validation,setValidation]=useState('');
  const alive=useRef(true);
  const busy=useRef(false);
  useEffect(() => { alive.current=true; return () => { alive.current=false; }; },[]);
  const current=() => alive.current && cache.getQueryData<BrowserSessionResponse | null>(SESSION_KEY)?.session_id===sid;
  const history=useQuery({queryKey:['messages',sid],queryFn:({signal})=>api<ChatHistoryResponse>(`/api/v1/sessions/${sid}/messages`,{signal})});
  const send=useMutation({mutationFn:(operation:Operation)=>api<MessageResponse>(`/api/v1/sessions/${sid}/messages`,{method:'POST',mutationKey:operation.key,body:{text:operation.text,language:operation.language}}),
    onSuccess:() => {
      void cache.invalidateQueries({predicate:query=>['messages','activities','summary','reductions'].includes(String(query.queryKey[0])) && query.queryKey.includes(sid)});
      if (!current()) return;
      setQueued(null); setText(''); saveDraft(`${storage}:text`,''); saveDraft(`${storage}:operation`,'null');
    }, onError:error => {
      if (!current()) return;
      if(error instanceof ApiError && error.status>=400 && error.status<500 && error.code!=='SESSION_BUSY') { setQueued(null); saveDraft(`${storage}:operation`,'null'); }
    },onSettled:()=>{busy.current=false;},
  });
  function submit(event?:FormEvent) {
    event?.preventDefault();
    if(busy.current || send.isPending) return;
    if(!queued && (!text.trim() || text.length>4000)) {setValidation('Write a message between 1 and 4000 characters.'); return;}
    const operation=queued ?? {text:text.trim(),language,key:crypto.randomUUID()};
    setValidation(''); busy.current=true; setQueued(operation); saveDraft(`${storage}:operation`,JSON.stringify(operation));
    send.mutate(operation);
  }
  const locked=Boolean(queued) || send.isPending;
  return <><PageHeading eyebrow="TRACKER AND COACH" title="Talk through your everyday impact">Chat and manual entry now share your session’s saved activities.</PageHeading>
    <section className="panel integrated-chat"><div className="chat-heading"><span className="icon-tile"><Bot size={24}/></span><div><h2>Dhrishti Carbon Coach</h2><p>Coordinator · Tracker · Coach</p></div><span className="soft-tag">{session!.chat_mode==='mock'?'MOCK CONNECTION':session!.chat_mode==='configured'?'PROVIDER CONFIGURED':'PROVIDER UNAVAILABLE'}</span></div>
      <div className="chat-transcript" role="log" aria-label="Conversation" aria-live="polite">
        {history.isPending?<Loading label="Restoring your conversation…"/>:history.error?<ErrorNotice error={history.error} retry={()=>{void history.refetch();}}/>:!history.data?.messages.length?<div className="chat-empty"><MessageCircle size={36} strokeWidth={1.2}/><h3>Start with one activity or question.</h3><p>Give explicit quantities and regions. For a car journey, include how many people travelled. Estimates use the approved UK references and global food averages.</p></div>:history.data.messages.map(message=><article className={`chat-message ${message.role}`} key={message.id}><div className="chat-message-label">{message.role==='user'?'You':'Carbon Coach'}<time dateTime={message.created_at}>{new Intl.DateTimeFormat('en',{hour:'numeric',minute:'2-digit',timeZone:session!.timezone}).format(new Date(message.created_at))}</time></div><p>{message.text}</p>{message.status==='partial_failure'&&<small>Turn interrupted. Confirmed receipts above are preserved.</small>}{(message.tool_calls??[]).length>0&&<details><summary>Tool evidence</summary><ul>{(message.tool_calls??[]).map((name,index)=><li key={`${name}:${index}`}>{name}</li>)}</ul></details>}</article>)}
        {send.isPending&&<p className="chat-processing" role="status"><LoaderCircle className="spin" size={17}/>Working through the specialist tools…</p>}
      </div>
      {queued&&!send.isPending&&<div className="notice">The last request is unconfirmed. Retry uses its original key and message; it will not replay an acknowledged operation.</div>}
      {send.error&&<ErrorNotice error={send.error}/>}
      <form className="chat-composer" onSubmit={submit}><div className="composer-heading"><label htmlFor="chat-text">Your message</label><select aria-label="Reply language" value={queued?.language??language} disabled={locked} onChange={event=>setLanguage(event.target.value as Language)}><option value="en">English</option><option value="hi">हिन्दी</option><option value="te">తెలుగు</option></select></div><textarea id="chat-text" value={queued?.text??text} maxLength={4000} disabled={locked} rows={3} placeholder="Describe an activity, ask for your logged total, or explore an alternative…" onChange={event=>{setText(event.target.value);saveDraft(`${storage}:text`,event.target.value);}} onKeyDown={event=>{if(event.key==='Enter'&&(event.ctrlKey||event.metaKey)){event.preventDefault();submit();}}}/>{validation&&<small className="field-error" role="alert">{validation}</small>}<div className="composer-actions"><small>Ctrl or ⌘ + Enter to send. Avoid sensitive information.</small><button className="button button-primary" disabled={send.isPending}>{send.isPending?'Working…':queued?'Retry safely':'Send message'}<Send size={15}/></button></div></form>
    </section><p className="chat-footnote"><ShieldCheck size={15}/>Quantitative answers are rendered from tool receipts. Some audit details remain in English. <Link to="/sources">View sources <ChevronRight size={13}/></Link></p>
  </>;
}
