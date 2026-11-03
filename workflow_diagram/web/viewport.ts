import {useLayoutEffect, useRef, useState} from 'react';

export interface DiagramFocus {key:string;label:string;group?:string;module?:string}
const MIN_ZOOM = .25, MAX_ZOOM = 1.6;
const bounded = (value:number) => Math.max(MIN_ZOOM,Math.min(MAX_ZOOM,value));

/** Camera state is local UI only. Measurements run on user action/resize, never on polling. */
export function useDiagramViewport(active:boolean, contextKey:string, motionPaused:boolean) {
  const canvas = useRef<HTMLDivElement>(null);
  const topology = useRef<HTMLDivElement>(null);
  const [zoom,setZoom] = useState(.8);
  const [focus,setFocus] = useState<DiagramFocus|null>(null);
  const [request,setRequest] = useState(0);
  const mode = useRef<'overview'|'manual'|'focus'>('overview');
  const pending = useRef<DiagramFocus|'overview'|null>('overview');
  const context = useRef(contextKey);
  const camera = useRef<{left:number;top:number;animate:boolean}|null>(null);
  const scrollPosition = useRef({left:0,top:0});
  const previouslyActive = useRef(active);
  const measuredSize = useRef('');
  const selected = useRef(focus);
  selected.current=focus;
  const zoomValue = useRef(zoom);
  zoomValue.current=zoom;

  const overview = () => {
    setFocus(null);mode.current='overview';pending.current='overview';setRequest(v=>v+1);
  };
  const select = (target:DiagramFocus) => {
    setFocus(target);mode.current='focus';pending.current=target;setRequest(v=>v+1);
  };
  const changeZoom = (value:number) => {
    const el=canvas.current,next=bounded(value),previous=zoomValue.current;
    mode.current='manual';pending.current=null;
    if(el)camera.current={left:(el.scrollLeft+el.clientWidth/2)*next/previous-el.clientWidth/2,top:(el.scrollTop+el.clientHeight/2)*next/previous-el.clientHeight/2,animate:false};
    setZoom(next);setRequest(v=>v+1);
  };

  useLayoutEffect(()=>{
    if(context.current!==contextKey){context.current=contextKey;setFocus(null);mode.current='overview';pending.current='overview';camera.current=null;scrollPosition.current={left:0,top:0};setRequest(v=>v+1)}
  },[contextKey]);

  useLayoutEffect(()=>{
    if(active&&!previouslyActive.current&&!pending.current)camera.current={...scrollPosition.current,animate:false};
    previouslyActive.current=active;
    const host=canvas.current;
    if(!active||!host)return;
    const remember=()=>{if(host.clientWidth)scrollPosition.current={left:host.scrollLeft,top:host.scrollTop}};
    host.addEventListener('scroll',remember,{passive:true});
    return()=>host.removeEventListener('scroll',remember);
  },[active]);

  useLayoutEffect(()=>{
    if(!active)return;
    const host=canvas.current,graph=topology.current;
    if(!host||!graph)return;
    const intent=pending.current;
    if(intent){
      pending.current=null;
      const target=intent==='overview'?graph:Array.from(graph.querySelectorAll<HTMLElement>('[data-wd-focus]')).find(el=>el.dataset.wdFocus===intent.key);
      if(!target){setFocus(null);mode.current='overview';return}
      const scale=zoomValue.current,rect=target.getBoundingClientRect(),origin=graph.getBoundingClientRect();
      const width=rect.width/scale,height=rect.height/scale;
      if(!width||!height)return;
      const next=bounded(Math.min(intent==='overview'?.85:1.1,(host.clientWidth-48)/width,(host.clientHeight-48)/height));
      camera.current={left:(rect.left-origin.left)/scale*next+width*next/2-host.clientWidth/2,top:(rect.top-origin.top)/scale*next+height*next/2-host.clientHeight/2,animate:intent!=='overview'};
      if(Math.abs(next-scale)>.001){setZoom(next);return}
    }
    if(camera.current){
      const position=camera.current;camera.current=null;
      const reduce=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      host.scrollTo({left:Math.max(0,position.left),top:Math.max(0,position.top),behavior:position.animate&&!motionPaused&&!reduce?'smooth':'instant'});
      if(!position.animate||motionPaused||reduce)scrollPosition.current={left:host.scrollLeft,top:host.scrollTop};
    }
  },[active,contextKey,request,zoom,motionPaused]);

  useLayoutEffect(()=>{
    if(!active||!canvas.current||!topology.current)return;
    let frame=0;
    const observer=new ResizeObserver(()=>{
      const host=canvas.current,graph=topology.current;
      if(!host||!graph||!host.clientWidth)return;
      const size=[host.clientWidth,host.clientHeight,graph.offsetWidth,graph.offsetHeight].join(':');
      if(size===measuredSize.current)return;
      measuredSize.current=size;
      if(mode.current==='manual')return;
      cancelAnimationFrame(frame);
      frame=requestAnimationFrame(()=>{
        if(mode.current==='manual')return;
        pending.current=mode.current==='overview'?'overview':selected.current;
        if(pending.current)setRequest(v=>v+1);
      });
    });
    observer.observe(canvas.current);observer.observe(topology.current,{box:'border-box'});
    return()=>{observer.disconnect();cancelAnimationFrame(frame)};
  },[active]);

  return {canvas,topology,zoom,focus,select,overview,changeZoom,minZoom:MIN_ZOOM,maxZoom:MAX_ZOOM};
}
