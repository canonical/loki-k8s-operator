import{r as a,c as Le,b as V}from"./react-core-D_V7s-9r.js";import{c as fe,u as A,a as ee,j as d,P as _,d as E,g as kt,q as Ve,f as Be,A as Nt,p as q,h as Mt,i as jt,R as At,S as Ot,F as Dt,D as Lt,C as Vt,e as Ee,k as Bt,V as Ht,b as Gt,n as Ft,o as Wt}from"./radix-core-mDeFS0Pz.js";import{c as Kt,a as Oe,u as He,b as Ge,R as Ut,I as $t}from"./radix-navigation-WDVJ59Wc.js";function _e(t){const s=a.useRef({value:t,previous:t});return a.useMemo(()=>(s.current.value!==t&&(s.current.previous=s.current.value,s.current.value=t),s.current.previous),[t])}var ke="Checkbox",[zt,_o]=fe(ke),[qt,Xt]=zt(ke),Fe=a.forwardRef((t,s)=>{const{__scopeCheckbox:e,name:c,checked:r,defaultChecked:i,required:n,disabled:o,value:l="on",onCheckedChange:u,form:h,...v}=t,[S,y]=a.useState(null),w=A(s,b=>y(b)),p=a.useRef(!1),x=S?h||!!S.closest("form"):!0,[C=!1,f]=ee({prop:r,defaultProp:i,onChange:u}),m=a.useRef(C);return a.useEffect(()=>{const b=S==null?void 0:S.form;if(b){const k=()=>f(m.current);return b.addEventListener("reset",k),()=>b.removeEventListener("reset",k)}},[S,f]),d.jsxs(qt,{scope:e,state:C,disabled:o,children:[d.jsx(_.button,{type:"button",role:"checkbox","aria-checked":z(C)?"mixed":C,"aria-required":n,"data-state":Ue(C),"data-disabled":o?"":void 0,disabled:o,value:l,...v,ref:w,onKeyDown:E(t.onKeyDown,b=>{b.key==="Enter"&&b.preventDefault()}),onClick:E(t.onClick,b=>{f(k=>z(k)?!0:!k),x&&(p.current=b.isPropagationStopped(),p.current||b.stopPropagation())})}),x&&d.jsx(Yt,{control:S,bubbles:!p.current,name:c,value:l,checked:C,required:n,disabled:o,form:h,style:{transform:"translateX(-100%)"},defaultChecked:z(i)?!1:i})]})});Fe.displayName=ke;var We="CheckboxIndicator",Ke=a.forwardRef((t,s)=>{const{__scopeCheckbox:e,forceMount:c,...r}=t,i=Xt(We,e);return d.jsx(kt,{present:c||z(i.state)||i.state===!0,children:d.jsx(_.span,{"data-state":Ue(i.state),"data-disabled":i.disabled?"":void 0,...r,ref:s,style:{pointerEvents:"none",...t.style}})})});Ke.displayName=We;var Yt=t=>{const{control:s,checked:e,bubbles:c=!0,defaultChecked:r,...i}=t,n=a.useRef(null),o=_e(e),l=Ve(s);a.useEffect(()=>{const h=n.current,v=window.HTMLInputElement.prototype,y=Object.getOwnPropertyDescriptor(v,"checked").set;if(o!==e&&y){const w=new Event("click",{bubbles:c});h.indeterminate=z(e),y.call(h,z(e)?!1:e),h.dispatchEvent(w)}},[o,e,c]);const u=a.useRef(z(e)?!1:e);return d.jsx("input",{type:"checkbox","aria-hidden":!0,defaultChecked:r??u.current,...i,tabIndex:-1,ref:n,style:{...t.style,...l,position:"absolute",pointerEvents:"none",opacity:0,margin:0}})};function z(t){return t==="indeterminate"}function Ue(t){return z(t)?"indeterminate":t?"checked":"unchecked"}var ko=Fe,No=Ke,Zt=[" ","Enter","ArrowUp","ArrowDown"],Jt=[" ","Enter"],le="Select",[he,me,Qt]=Kt(le),[ne,Mo]=fe(le,[Qt,Be]),ge=Be(),[eo,X]=ne(le),[to,oo]=ne(le),$e=t=>{const{__scopeSelect:s,children:e,open:c,defaultOpen:r,onOpenChange:i,value:n,defaultValue:o,onValueChange:l,dir:u,name:h,autoComplete:v,disabled:S,required:y,form:w}=t,p=ge(s),[x,C]=a.useState(null),[f,m]=a.useState(null),[b,k]=a.useState(!1),se=He(u),[N=!1,D]=ee({prop:c,defaultProp:r,onChange:i}),[K,Z]=ee({prop:n,defaultProp:o,onChange:l}),B=a.useRef(null),H=x?w||!!x.closest("form"):!0,[U,G]=a.useState(new Set),F=Array.from(U).map(M=>M.props.value).join(";");return d.jsx(Wt,{...p,children:d.jsxs(eo,{required:y,scope:s,trigger:x,onTriggerChange:C,valueNode:f,onValueNodeChange:m,valueNodeHasChildren:b,onValueNodeHasChildrenChange:k,contentId:Ee(),value:K,onValueChange:Z,open:N,onOpenChange:D,dir:se,triggerPointerDownPosRef:B,disabled:S,children:[d.jsx(he.Provider,{scope:s,children:d.jsx(to,{scope:t.__scopeSelect,onNativeOptionAdd:a.useCallback(M=>{G(L=>new Set(L).add(M))},[]),onNativeOptionRemove:a.useCallback(M=>{G(L=>{const W=new Set(L);return W.delete(M),W})},[]),children:e})}),H?d.jsxs(vt,{"aria-hidden":!0,required:y,tabIndex:-1,name:h,autoComplete:v,value:K,onChange:M=>Z(M.target.value),disabled:S,form:w,children:[K===void 0?d.jsx("option",{value:""}):null,Array.from(U)]},F):null]})})};$e.displayName=le;var ze="SelectTrigger",qe=a.forwardRef((t,s)=>{const{__scopeSelect:e,disabled:c=!1,...r}=t,i=ge(e),n=X(ze,e),o=n.disabled||c,l=A(s,n.onTriggerChange),u=me(e),h=a.useRef("touch"),[v,S,y]=xt(p=>{const x=u().filter(m=>!m.disabled),C=x.find(m=>m.value===n.value),f=St(x,p,C);f!==void 0&&n.onValueChange(f.value)}),w=p=>{o||(n.onOpenChange(!0),y()),p&&(n.triggerPointerDownPosRef.current={x:Math.round(p.pageX),y:Math.round(p.pageY)})};return d.jsx(Nt,{asChild:!0,...i,children:d.jsx(_.button,{type:"button",role:"combobox","aria-controls":n.contentId,"aria-expanded":n.open,"aria-required":n.required,"aria-autocomplete":"none",dir:n.dir,"data-state":n.open?"open":"closed",disabled:o,"data-disabled":o?"":void 0,"data-placeholder":gt(n.value)?"":void 0,...r,ref:l,onClick:E(r.onClick,p=>{p.currentTarget.focus(),h.current!=="mouse"&&w(p)}),onPointerDown:E(r.onPointerDown,p=>{h.current=p.pointerType;const x=p.target;x.hasPointerCapture(p.pointerId)&&x.releasePointerCapture(p.pointerId),p.button===0&&p.ctrlKey===!1&&p.pointerType==="mouse"&&(w(p),p.preventDefault())}),onKeyDown:E(r.onKeyDown,p=>{const x=v.current!=="";!(p.ctrlKey||p.altKey||p.metaKey)&&p.key.length===1&&S(p.key),!(x&&p.key===" ")&&Zt.includes(p.key)&&(w(),p.preventDefault())})})})});qe.displayName=ze;var Xe="SelectValue",Ye=a.forwardRef((t,s)=>{const{__scopeSelect:e,className:c,style:r,children:i,placeholder:n="",...o}=t,l=X(Xe,e),{onValueNodeHasChildrenChange:u}=l,h=i!==void 0,v=A(s,l.onValueNodeChange);return q(()=>{u(h)},[u,h]),d.jsx(_.span,{...o,ref:v,style:{pointerEvents:"none"},children:gt(l.value)?d.jsx(d.Fragment,{children:n}):i})});Ye.displayName=Xe;var no="SelectIcon",Ze=a.forwardRef((t,s)=>{const{__scopeSelect:e,children:c,...r}=t;return d.jsx(_.span,{"aria-hidden":!0,...r,ref:s,children:c||"▼"})});Ze.displayName=no;var ro="SelectPortal",Je=t=>d.jsx(Ft,{asChild:!0,...t});Je.displayName=ro;var te="SelectContent",Qe=a.forwardRef((t,s)=>{const e=X(te,t.__scopeSelect),[c,r]=a.useState();if(q(()=>{r(new DocumentFragment)},[]),!e.open){const i=c;return i?Le.createPortal(d.jsx(et,{scope:t.__scopeSelect,children:d.jsx(he.Slot,{scope:t.__scopeSelect,children:d.jsx("div",{children:t.children})})}),i):null}return d.jsx(tt,{...t,ref:s})});Qe.displayName=te;var O=10,[et,Y]=ne(te),so="SelectContentImpl",tt=a.forwardRef((t,s)=>{const{__scopeSelect:e,position:c="item-aligned",onCloseAutoFocus:r,onEscapeKeyDown:i,onPointerDownOutside:n,side:o,sideOffset:l,align:u,alignOffset:h,arrowPadding:v,collisionBoundary:S,collisionPadding:y,sticky:w,hideWhenDetached:p,avoidCollisions:x,...C}=t,f=X(te,e),[m,b]=a.useState(null),[k,se]=a.useState(null),N=A(s,g=>b(g)),[D,K]=a.useState(null),[Z,B]=a.useState(null),H=me(e),[U,G]=a.useState(!1),F=a.useRef(!1);a.useEffect(()=>{if(m)return Mt(m)},[m]),jt();const M=a.useCallback(g=>{const[R,...j]=H().map(T=>T.ref.current),[I]=j.slice(-1),P=document.activeElement;for(const T of g)if(T===P||(T==null||T.scrollIntoView({block:"nearest"}),T===R&&k&&(k.scrollTop=0),T===I&&k&&(k.scrollTop=k.scrollHeight),T==null||T.focus(),document.activeElement!==P))return},[H,k]),L=a.useCallback(()=>M([D,m]),[M,D,m]);a.useEffect(()=>{U&&L()},[U,L]);const{onOpenChange:W,triggerPointerDownPosRef:$}=f;a.useEffect(()=>{if(m){let g={x:0,y:0};const R=I=>{var P,T;g={x:Math.abs(Math.round(I.pageX)-(((P=$.current)==null?void 0:P.x)??0)),y:Math.abs(Math.round(I.pageY)-(((T=$.current)==null?void 0:T.y)??0))}},j=I=>{g.x<=10&&g.y<=10?I.preventDefault():m.contains(I.target)||W(!1),document.removeEventListener("pointermove",R),$.current=null};return $.current!==null&&(document.addEventListener("pointermove",R),document.addEventListener("pointerup",j,{capture:!0,once:!0})),()=>{document.removeEventListener("pointermove",R),document.removeEventListener("pointerup",j,{capture:!0})}}},[m,W,$]),a.useEffect(()=>{const g=()=>W(!1);return window.addEventListener("blur",g),window.addEventListener("resize",g),()=>{window.removeEventListener("blur",g),window.removeEventListener("resize",g)}},[W]);const[ve,ie]=xt(g=>{const R=H().filter(P=>!P.disabled),j=R.find(P=>P.ref.current===document.activeElement),I=St(R,g,j);I&&setTimeout(()=>I.ref.current.focus())}),xe=a.useCallback((g,R,j)=>{const I=!F.current&&!j;(f.value!==void 0&&f.value===R||I)&&(K(g),I&&(F.current=!0))},[f.value]),Se=a.useCallback(()=>m==null?void 0:m.focus(),[m]),oe=a.useCallback((g,R,j)=>{const I=!F.current&&!j;(f.value!==void 0&&f.value===R||I)&&B(g)},[f.value]),de=c==="popper"?be:ot,ae=de===be?{side:o,sideOffset:l,align:u,alignOffset:h,arrowPadding:v,collisionBoundary:S,collisionPadding:y,sticky:w,hideWhenDetached:p,avoidCollisions:x}:{};return d.jsx(et,{scope:e,content:m,viewport:k,onViewportChange:se,itemRefCallback:xe,selectedItem:D,onItemLeave:Se,itemTextRefCallback:oe,focusSelectedItem:L,selectedItemText:Z,position:c,isPositioned:U,searchRef:ve,children:d.jsx(At,{as:Ot,allowPinchZoom:!0,children:d.jsx(Dt,{asChild:!0,trapped:f.open,onMountAutoFocus:g=>{g.preventDefault()},onUnmountAutoFocus:E(r,g=>{var R;(R=f.trigger)==null||R.focus({preventScroll:!0}),g.preventDefault()}),children:d.jsx(Lt,{asChild:!0,disableOutsidePointerEvents:!0,onEscapeKeyDown:i,onPointerDownOutside:n,onFocusOutside:g=>g.preventDefault(),onDismiss:()=>f.onOpenChange(!1),children:d.jsx(de,{role:"listbox",id:f.contentId,"data-state":f.open?"open":"closed",dir:f.dir,onContextMenu:g=>g.preventDefault(),...C,...ae,onPlaced:()=>G(!0),ref:N,style:{display:"flex",flexDirection:"column",outline:"none",...C.style},onKeyDown:E(C.onKeyDown,g=>{const R=g.ctrlKey||g.altKey||g.metaKey;if(g.key==="Tab"&&g.preventDefault(),!R&&g.key.length===1&&ie(g.key),["ArrowUp","ArrowDown","Home","End"].includes(g.key)){let I=H().filter(P=>!P.disabled).map(P=>P.ref.current);if(["ArrowUp","End"].includes(g.key)&&(I=I.slice().reverse()),["ArrowUp","ArrowDown"].includes(g.key)){const P=g.target,T=I.indexOf(P);I=I.slice(T+1)}setTimeout(()=>M(I)),g.preventDefault()}})})})})})})});tt.displayName=so;var ao="SelectItemAlignedPosition",ot=a.forwardRef((t,s)=>{const{__scopeSelect:e,onPlaced:c,...r}=t,i=X(te,e),n=Y(te,e),[o,l]=a.useState(null),[u,h]=a.useState(null),v=A(s,N=>h(N)),S=me(e),y=a.useRef(!1),w=a.useRef(!0),{viewport:p,selectedItem:x,selectedItemText:C,focusSelectedItem:f}=n,m=a.useCallback(()=>{if(i.trigger&&i.valueNode&&o&&u&&p&&x&&C){const N=i.trigger.getBoundingClientRect(),D=u.getBoundingClientRect(),K=i.valueNode.getBoundingClientRect(),Z=C.getBoundingClientRect();if(i.dir!=="rtl"){const P=Z.left-D.left,T=K.left-P,J=N.left-T,Q=N.width+J,Ce=Math.max(Q,D.width),we=window.innerWidth-O,ye=Oe(T,[O,Math.max(O,we-Ce)]);o.style.minWidth=Q+"px",o.style.left=ye+"px"}else{const P=D.right-Z.right,T=window.innerWidth-K.right-P,J=window.innerWidth-N.right-T,Q=N.width+J,Ce=Math.max(Q,D.width),we=window.innerWidth-O,ye=Oe(T,[O,Math.max(O,we-Ce)]);o.style.minWidth=Q+"px",o.style.right=ye+"px"}const B=S(),H=window.innerHeight-O*2,U=p.scrollHeight,G=window.getComputedStyle(u),F=parseInt(G.borderTopWidth,10),M=parseInt(G.paddingTop,10),L=parseInt(G.borderBottomWidth,10),W=parseInt(G.paddingBottom,10),$=F+M+U+W+L,ve=Math.min(x.offsetHeight*5,$),ie=window.getComputedStyle(p),xe=parseInt(ie.paddingTop,10),Se=parseInt(ie.paddingBottom,10),oe=N.top+N.height/2-O,de=H-oe,ae=x.offsetHeight/2,g=x.offsetTop+ae,R=F+M+g,j=$-R;if(R<=oe){const P=B.length>0&&x===B[B.length-1].ref.current;o.style.bottom="0px";const T=u.clientHeight-p.offsetTop-p.offsetHeight,J=Math.max(de,ae+(P?Se:0)+T+L),Q=R+J;o.style.height=Q+"px"}else{const P=B.length>0&&x===B[0].ref.current;o.style.top="0px";const J=Math.max(oe,F+p.offsetTop+(P?xe:0)+ae)+j;o.style.height=J+"px",p.scrollTop=R-oe+p.offsetTop}o.style.margin=`${O}px 0`,o.style.minHeight=ve+"px",o.style.maxHeight=H+"px",c==null||c(),requestAnimationFrame(()=>y.current=!0)}},[S,i.trigger,i.valueNode,o,u,p,x,C,i.dir,c]);q(()=>m(),[m]);const[b,k]=a.useState();q(()=>{u&&k(window.getComputedStyle(u).zIndex)},[u]);const se=a.useCallback(N=>{N&&w.current===!0&&(m(),f==null||f(),w.current=!1)},[m,f]);return d.jsx(lo,{scope:e,contentWrapper:o,shouldExpandOnScrollRef:y,onScrollButtonChange:se,children:d.jsx("div",{ref:l,style:{display:"flex",flexDirection:"column",position:"fixed",zIndex:b},children:d.jsx(_.div,{...r,ref:v,style:{boxSizing:"border-box",maxHeight:"100%",...r.style}})})})});ot.displayName=ao;var co="SelectPopperPosition",be=a.forwardRef((t,s)=>{const{__scopeSelect:e,align:c="start",collisionPadding:r=O,...i}=t,n=ge(e);return d.jsx(Vt,{...n,...i,ref:s,align:c,collisionPadding:r,style:{boxSizing:"border-box",...i.style,"--radix-select-content-transform-origin":"var(--radix-popper-transform-origin)","--radix-select-content-available-width":"var(--radix-popper-available-width)","--radix-select-content-available-height":"var(--radix-popper-available-height)","--radix-select-trigger-width":"var(--radix-popper-anchor-width)","--radix-select-trigger-height":"var(--radix-popper-anchor-height)"}})});be.displayName=co;var[lo,Ne]=ne(te,{}),Pe="SelectViewport",nt=a.forwardRef((t,s)=>{const{__scopeSelect:e,nonce:c,...r}=t,i=Y(Pe,e),n=Ne(Pe,e),o=A(s,i.onViewportChange),l=a.useRef(0);return d.jsxs(d.Fragment,{children:[d.jsx("style",{dangerouslySetInnerHTML:{__html:"[data-radix-select-viewport]{scrollbar-width:none;-ms-overflow-style:none;-webkit-overflow-scrolling:touch;}[data-radix-select-viewport]::-webkit-scrollbar{display:none}"},nonce:c}),d.jsx(he.Slot,{scope:e,children:d.jsx(_.div,{"data-radix-select-viewport":"",role:"presentation",...r,ref:o,style:{position:"relative",flex:1,overflow:"hidden auto",...r.style},onScroll:E(r.onScroll,u=>{const h=u.currentTarget,{contentWrapper:v,shouldExpandOnScrollRef:S}=n;if(S!=null&&S.current&&v){const y=Math.abs(l.current-h.scrollTop);if(y>0){const w=window.innerHeight-O*2,p=parseFloat(v.style.minHeight),x=parseFloat(v.style.height),C=Math.max(p,x);if(C<w){const f=C+y,m=Math.min(w,f),b=f-m;v.style.height=m+"px",v.style.bottom==="0px"&&(h.scrollTop=b>0?b:0,v.style.justifyContent="flex-end")}}}l.current=h.scrollTop})})})]})});nt.displayName=Pe;var rt="SelectGroup",[io,uo]=ne(rt),po=a.forwardRef((t,s)=>{const{__scopeSelect:e,...c}=t,r=Ee();return d.jsx(io,{scope:e,id:r,children:d.jsx(_.div,{role:"group","aria-labelledby":r,...c,ref:s})})});po.displayName=rt;var st="SelectLabel",at=a.forwardRef((t,s)=>{const{__scopeSelect:e,...c}=t,r=uo(st,e);return d.jsx(_.div,{id:r.id,...c,ref:s})});at.displayName=st;var ue="SelectItem",[fo,ct]=ne(ue),lt=a.forwardRef((t,s)=>{const{__scopeSelect:e,value:c,disabled:r=!1,textValue:i,...n}=t,o=X(ue,e),l=Y(ue,e),u=o.value===c,[h,v]=a.useState(i??""),[S,y]=a.useState(!1),w=A(s,f=>{var m;return(m=l.itemRefCallback)==null?void 0:m.call(l,f,c,r)}),p=Ee(),x=a.useRef("touch"),C=()=>{r||(o.onValueChange(c),o.onOpenChange(!1))};if(c==="")throw new Error("A <Select.Item /> must have a value prop that is not an empty string. This is because the Select value can be set to an empty string to clear the selection and show the placeholder.");return d.jsx(fo,{scope:e,value:c,disabled:r,textId:p,isSelected:u,onItemTextChange:a.useCallback(f=>{v(m=>m||((f==null?void 0:f.textContent)??"").trim())},[]),children:d.jsx(he.ItemSlot,{scope:e,value:c,disabled:r,textValue:h,children:d.jsx(_.div,{role:"option","aria-labelledby":p,"data-highlighted":S?"":void 0,"aria-selected":u&&S,"data-state":u?"checked":"unchecked","aria-disabled":r||void 0,"data-disabled":r?"":void 0,tabIndex:r?void 0:-1,...n,ref:w,onFocus:E(n.onFocus,()=>y(!0)),onBlur:E(n.onBlur,()=>y(!1)),onClick:E(n.onClick,()=>{x.current!=="mouse"&&C()}),onPointerUp:E(n.onPointerUp,()=>{x.current==="mouse"&&C()}),onPointerDown:E(n.onPointerDown,f=>{x.current=f.pointerType}),onPointerMove:E(n.onPointerMove,f=>{var m;x.current=f.pointerType,r?(m=l.onItemLeave)==null||m.call(l):x.current==="mouse"&&f.currentTarget.focus({preventScroll:!0})}),onPointerLeave:E(n.onPointerLeave,f=>{var m;f.currentTarget===document.activeElement&&((m=l.onItemLeave)==null||m.call(l))}),onKeyDown:E(n.onKeyDown,f=>{var b;((b=l.searchRef)==null?void 0:b.current)!==""&&f.key===" "||(Jt.includes(f.key)&&C(),f.key===" "&&f.preventDefault())})})})})});lt.displayName=ue;var ce="SelectItemText",it=a.forwardRef((t,s)=>{const{__scopeSelect:e,className:c,style:r,...i}=t,n=X(ce,e),o=Y(ce,e),l=ct(ce,e),u=oo(ce,e),[h,v]=a.useState(null),S=A(s,C=>v(C),l.onItemTextChange,C=>{var f;return(f=o.itemTextRefCallback)==null?void 0:f.call(o,C,l.value,l.disabled)}),y=h==null?void 0:h.textContent,w=a.useMemo(()=>d.jsx("option",{value:l.value,disabled:l.disabled,children:y},l.value),[l.disabled,l.value,y]),{onNativeOptionAdd:p,onNativeOptionRemove:x}=u;return q(()=>(p(w),()=>x(w)),[p,x,w]),d.jsxs(d.Fragment,{children:[d.jsx(_.span,{id:l.textId,...i,ref:S}),l.isSelected&&n.valueNode&&!n.valueNodeHasChildren?Le.createPortal(i.children,n.valueNode):null]})});it.displayName=ce;var dt="SelectItemIndicator",ut=a.forwardRef((t,s)=>{const{__scopeSelect:e,...c}=t;return ct(dt,e).isSelected?d.jsx(_.span,{"aria-hidden":!0,...c,ref:s}):null});ut.displayName=dt;var Te="SelectScrollUpButton",pt=a.forwardRef((t,s)=>{const e=Y(Te,t.__scopeSelect),c=Ne(Te,t.__scopeSelect),[r,i]=a.useState(!1),n=A(s,c.onScrollButtonChange);return q(()=>{if(e.viewport&&e.isPositioned){let o=function(){const u=l.scrollTop>0;i(u)};const l=e.viewport;return o(),l.addEventListener("scroll",o),()=>l.removeEventListener("scroll",o)}},[e.viewport,e.isPositioned]),r?d.jsx(ht,{...t,ref:n,onAutoScroll:()=>{const{viewport:o,selectedItem:l}=e;o&&l&&(o.scrollTop=o.scrollTop-l.offsetHeight)}}):null});pt.displayName=Te;var Ie="SelectScrollDownButton",ft=a.forwardRef((t,s)=>{const e=Y(Ie,t.__scopeSelect),c=Ne(Ie,t.__scopeSelect),[r,i]=a.useState(!1),n=A(s,c.onScrollButtonChange);return q(()=>{if(e.viewport&&e.isPositioned){let o=function(){const u=l.scrollHeight-l.clientHeight,h=Math.ceil(l.scrollTop)<u;i(h)};const l=e.viewport;return o(),l.addEventListener("scroll",o),()=>l.removeEventListener("scroll",o)}},[e.viewport,e.isPositioned]),r?d.jsx(ht,{...t,ref:n,onAutoScroll:()=>{const{viewport:o,selectedItem:l}=e;o&&l&&(o.scrollTop=o.scrollTop+l.offsetHeight)}}):null});ft.displayName=Ie;var ht=a.forwardRef((t,s)=>{const{__scopeSelect:e,onAutoScroll:c,...r}=t,i=Y("SelectScrollButton",e),n=a.useRef(null),o=me(e),l=a.useCallback(()=>{n.current!==null&&(window.clearInterval(n.current),n.current=null)},[]);return a.useEffect(()=>()=>l(),[l]),q(()=>{var h;const u=o().find(v=>v.ref.current===document.activeElement);(h=u==null?void 0:u.ref.current)==null||h.scrollIntoView({block:"nearest"})},[o]),d.jsx(_.div,{"aria-hidden":!0,...r,ref:s,style:{flexShrink:0,...r.style},onPointerDown:E(r.onPointerDown,()=>{n.current===null&&(n.current=window.setInterval(c,50))}),onPointerMove:E(r.onPointerMove,()=>{var u;(u=i.onItemLeave)==null||u.call(i),n.current===null&&(n.current=window.setInterval(c,50))}),onPointerLeave:E(r.onPointerLeave,()=>{l()})})}),ho="SelectSeparator",mt=a.forwardRef((t,s)=>{const{__scopeSelect:e,...c}=t;return d.jsx(_.div,{"aria-hidden":!0,...c,ref:s})});mt.displayName=ho;var Re="SelectArrow",mo=a.forwardRef((t,s)=>{const{__scopeSelect:e,...c}=t,r=ge(e),i=X(Re,e),n=Y(Re,e);return i.open&&n.position==="popper"?d.jsx(Bt,{...r,...c,ref:s}):null});mo.displayName=Re;function gt(t){return t===""||t===void 0}var vt=a.forwardRef((t,s)=>{const{value:e,...c}=t,r=a.useRef(null),i=A(s,r),n=_e(e);return a.useEffect(()=>{const o=r.current,l=window.HTMLSelectElement.prototype,h=Object.getOwnPropertyDescriptor(l,"value").set;if(n!==e&&h){const v=new Event("change",{bubbles:!0});h.call(o,e),o.dispatchEvent(v)}},[n,e]),d.jsx(Ht,{asChild:!0,children:d.jsx("select",{...c,ref:i,defaultValue:e})})});vt.displayName="BubbleSelect";function xt(t){const s=Gt(t),e=a.useRef(""),c=a.useRef(0),r=a.useCallback(n=>{const o=e.current+n;s(o),function l(u){e.current=u,window.clearTimeout(c.current),u!==""&&(c.current=window.setTimeout(()=>l(""),1e3))}(o)},[s]),i=a.useCallback(()=>{e.current="",window.clearTimeout(c.current)},[]);return a.useEffect(()=>()=>window.clearTimeout(c.current),[]),[e,r,i]}function St(t,s,e){const r=s.length>1&&Array.from(s).every(u=>u===s[0])?s[0]:s,i=e?t.indexOf(e):-1;let n=go(t,Math.max(i,0));r.length===1&&(n=n.filter(u=>u!==e));const l=n.find(u=>u.textValue.toLowerCase().startsWith(r.toLowerCase()));return l!==e?l:void 0}function go(t,s){return t.map((e,c)=>t[(s+c)%t.length])}var jo=$e,Ao=qe,Oo=Ye,Do=Ze,Lo=Je,Vo=Qe,Bo=nt,Ho=at,Go=lt,Fo=it,Wo=ut,Ko=pt,Uo=ft,$o=mt,Me="Switch",[vo,zo]=fe(Me),[xo,So]=vo(Me),Ct=a.forwardRef((t,s)=>{const{__scopeSwitch:e,name:c,checked:r,defaultChecked:i,required:n,disabled:o,value:l="on",onCheckedChange:u,form:h,...v}=t,[S,y]=a.useState(null),w=A(s,m=>y(m)),p=a.useRef(!1),x=S?h||!!S.closest("form"):!0,[C=!1,f]=ee({prop:r,defaultProp:i,onChange:u});return d.jsxs(xo,{scope:e,checked:C,disabled:o,children:[d.jsx(_.button,{type:"button",role:"switch","aria-checked":C,"aria-required":n,"data-state":bt(C),"data-disabled":o?"":void 0,disabled:o,value:l,...v,ref:w,onClick:E(t.onClick,m=>{f(b=>!b),x&&(p.current=m.isPropagationStopped(),p.current||m.stopPropagation())})}),x&&d.jsx(Co,{control:S,bubbles:!p.current,name:c,value:l,checked:C,required:n,disabled:o,form:h,style:{transform:"translateX(-100%)"}})]})});Ct.displayName=Me;var wt="SwitchThumb",yt=a.forwardRef((t,s)=>{const{__scopeSwitch:e,...c}=t,r=So(wt,e);return d.jsx(_.span,{"data-state":bt(r.checked),"data-disabled":r.disabled?"":void 0,...c,ref:s})});yt.displayName=wt;var Co=t=>{const{control:s,checked:e,bubbles:c=!0,...r}=t,i=a.useRef(null),n=_e(e),o=Ve(s);return a.useEffect(()=>{const l=i.current,u=window.HTMLInputElement.prototype,v=Object.getOwnPropertyDescriptor(u,"checked").set;if(n!==e&&v){const S=new Event("click",{bubbles:c});v.call(l,e),l.dispatchEvent(S)}},[n,e,c]),d.jsx("input",{type:"checkbox","aria-hidden":!0,defaultChecked:e,...r,tabIndex:-1,ref:i,style:{...t.style,...o,position:"absolute",pointerEvents:"none",opacity:0,margin:0}})};function bt(t){return t?"checked":"unchecked"}var qo=Ct,Xo=yt,wo="Toggle",je=a.forwardRef((t,s)=>{const{pressed:e,defaultPressed:c=!1,onPressedChange:r,...i}=t,[n=!1,o]=ee({prop:e,onChange:r,defaultProp:c});return d.jsx(_.button,{type:"button","aria-pressed":n,"data-state":n?"on":"off","data-disabled":t.disabled?"":void 0,...i,ref:s,onClick:E(t.onClick,()=>{t.disabled||o(!n)})})});je.displayName=wo;var Yo=je,re="ToggleGroup",[Pt,Zo]=fe(re,[Ge]),Tt=Ge(),Ae=V.forwardRef((t,s)=>{const{type:e,...c}=t;if(e==="single"){const r=c;return d.jsx(yo,{...r,ref:s})}if(e==="multiple"){const r=c;return d.jsx(bo,{...r,ref:s})}throw new Error(`Missing prop \`type\` expected on \`${re}\``)});Ae.displayName=re;var[It,Rt]=Pt(re),yo=V.forwardRef((t,s)=>{const{value:e,defaultValue:c,onValueChange:r=()=>{},...i}=t,[n,o]=ee({prop:e,defaultProp:c,onChange:r});return d.jsx(It,{scope:t.__scopeToggleGroup,type:"single",value:n?[n]:[],onItemActivate:o,onItemDeactivate:V.useCallback(()=>o(""),[o]),children:d.jsx(Et,{...i,ref:s})})}),bo=V.forwardRef((t,s)=>{const{value:e,defaultValue:c,onValueChange:r=()=>{},...i}=t,[n=[],o]=ee({prop:e,defaultProp:c,onChange:r}),l=V.useCallback(h=>o((v=[])=>[...v,h]),[o]),u=V.useCallback(h=>o((v=[])=>v.filter(S=>S!==h)),[o]);return d.jsx(It,{scope:t.__scopeToggleGroup,type:"multiple",value:n,onItemActivate:l,onItemDeactivate:u,children:d.jsx(Et,{...i,ref:s})})});Ae.displayName=re;var[Po,To]=Pt(re),Et=V.forwardRef((t,s)=>{const{__scopeToggleGroup:e,disabled:c=!1,rovingFocus:r=!0,orientation:i,dir:n,loop:o=!0,...l}=t,u=Tt(e),h=He(n),v={role:"group",dir:h,...l};return d.jsx(Po,{scope:e,rovingFocus:r,disabled:c,children:r?d.jsx(Ut,{asChild:!0,...u,orientation:i,dir:h,loop:o,children:d.jsx(_.div,{...v,ref:s})}):d.jsx(_.div,{...v,ref:s})})}),pe="ToggleGroupItem",_t=V.forwardRef((t,s)=>{const e=Rt(pe,t.__scopeToggleGroup),c=To(pe,t.__scopeToggleGroup),r=Tt(t.__scopeToggleGroup),i=e.value.includes(t.value),n=c.disabled||t.disabled,o={...t,pressed:i,disabled:n},l=V.useRef(null);return c.rovingFocus?d.jsx($t,{asChild:!0,...r,focusable:!n,active:i,ref:l,children:d.jsx(De,{...o,ref:s})}):d.jsx(De,{...o,ref:s})});_t.displayName=pe;var De=V.forwardRef((t,s)=>{const{__scopeToggleGroup:e,value:c,...r}=t,i=Rt(pe,e),n={role:"radio","aria-checked":t.pressed,"aria-pressed":void 0},o=i.type==="single"?n:void 0;return d.jsx(je,{...o,...r,ref:s,onPressedChange:l=>{l?i.onItemActivate(c):i.onItemDeactivate(c)}})}),Jo=Ae,Qo=_t;export{Vo as C,No as I,Ho as L,Lo as P,ko as R,Ko as S,Ao as T,Bo as V,Do as a,Uo as b,Go as c,Wo as d,Fo as e,$o as f,jo as g,Oo as h,qo as i,Xo as j,Yo as k,Jo as l,Qo as m};
