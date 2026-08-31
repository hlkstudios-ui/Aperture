"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

type Anchor = { top:number; left:number; right:number; bottom:number };
const HOVER_DELAY_MS=1250;

export function CatalogDescriptionPreview({title,description}:{title:string;description:string}) {
  const timer=useRef<ReturnType<typeof setTimeout>|null>(null);
  const [anchor,setAnchor]=useState<Anchor|null>(null);

  useEffect(()=>()=>{if(timer.current)clearTimeout(timer.current)},[]);

  function clearTimer(){if(timer.current){clearTimeout(timer.current);timer.current=null}}
  function show(target:HTMLElement){
    clearTimer();
    const rect=target.getBoundingClientRect();
    setAnchor({top:rect.top,left:rect.left,right:rect.right,bottom:rect.bottom});
  }
  function schedule(target:HTMLElement){clearTimer();timer.current=setTimeout(()=>show(target),HOVER_DELAY_MS)}
  function hide(){clearTimer();setAnchor(null)}

  const viewportWidth=typeof window==="undefined"?0:window.innerWidth;
  const width=Math.min(390,Math.max(280,viewportWidth-32));
  const preferredLeft=(anchor?.right??0)+14;
  const left=anchor?Math.max(16,preferredLeft+width<=viewportWidth-16?preferredLeft:anchor.left-width-14):16;
  const top=anchor?Math.max(16,Math.min(anchor.top-36,(typeof window==="undefined"?800:window.innerHeight)-260)):16;

  return <>
    <span
      className="catalog-card__description"
      onMouseEnter={event=>schedule(event.currentTarget)}
      onMouseLeave={hide}
    >{description}</span>
    {anchor&&typeof document!=="undefined"?createPortal(
      <aside role="tooltip" className="catalog-synopsis-popover" style={{top,left,width}}>
        <span>Full synopsis</span>
        <strong>{title}</strong>
        <p>{description}</p>
      </aside>,document.body):null}
  </>;
}
