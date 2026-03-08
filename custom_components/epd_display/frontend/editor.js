console.log("[EPD] editor.js loaded");
// ══════ Helpers ══════
function toast(m){const t=$('toast-el');t.textContent=m;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2200)}
function $(id){return document.getElementById(id)}
function closeModal(id){$(id).classList.remove('open')}
function getToken(){try{const a=JSON.parse(localStorage.getItem('hassTokens'));if(a&&a.access_token)return a.access_token}catch(e){}const p=new URLSearchParams(location.search);return p.get('token')||null}
function authH(){const t=getToken(),h={'Content-Type':'application/json'};if(t)h['Authorization']='Bearer '+t;return h}
function authHM(){const t=getToken(),h={};if(t)h['Authorization']='Bearer '+t;return h}

// ══════ Pages ══════
function showPage(n){document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));$('page-'+n).classList.add('active');document.querySelectorAll('.tab').forEach(t=>{if((n==='send'&&t.textContent.includes('发送'))||(n==='editor'&&t.textContent.includes('编辑'))||(n==='tpl'&&t.textContent.includes('模板')))t.classList.add('active')});if(n==='tpl')loadTemplateList()}

// ══════ Config ══════
let haConfig={canvas_options:[],dither_modes:[],defaults:{}};
async function loadConfig(){try{const r=await fetch('/api/epd_display/config',{headers:authH()});if(r.ok)haConfig=await r.json()}catch(e){}['send-canvas','send-url-canvas'].forEach(id=>{const s=$(id);s.innerHTML='';haConfig.canvas_options.forEach(c=>{const o=document.createElement('option');o.value=c;o.textContent=c;if(c===haConfig.defaults.canvas)o.selected=true;s.appendChild(o)})});['send-dither','send-url-dither'].forEach(id=>{const s=$(id);s.innerHTML='';haConfig.dither_modes.forEach(c=>{const o=document.createElement('option');o.value=c;o.textContent=c;if(c===haConfig.defaults.dither_mode)o.selected=true;s.appendChild(o)})})}
loadConfig();

// ══════ Send Page ══════
let uploadFileData=null;
$('upload-file').addEventListener('change',e=>{const f=e.target.files[0];if(!f)return;uploadFileData=f;$('upload-preview').src=URL.createObjectURL(f);$('upload-preview').style.display='block';$('drop-zone').querySelector('div').textContent=f.name});
$('drop-zone').addEventListener('dragover',e=>{e.preventDefault();$('drop-zone').classList.add('over')});
$('drop-zone').addEventListener('dragleave',()=>$('drop-zone').classList.remove('over'));
$('drop-zone').addEventListener('drop',e=>{e.preventDefault();$('drop-zone').classList.remove('over');const f=e.dataTransfer.files[0];if(!f)return;uploadFileData=f;$('upload-file').files=e.dataTransfer.files;$('upload-preview').src=URL.createObjectURL(f);$('upload-preview').style.display='block';$('drop-zone').querySelector('div').textContent=f.name});
async function sendUpload(){if(!uploadFileData){toast('请选择图片');return}const fd=new FormData();fd.append('image',uploadFileData);fd.append('canvas',$('send-canvas').value);fd.append('dither_mode',$('send-dither').value);try{const r=await fetch('/api/epd_display/upload',{method:'POST',headers:authHM(),body:fd});if(r.ok)toast('✅ 发送成功');else{const j=await r.json();toast('❌ '+j.error)}}catch(e){toast('❌ '+e.message)}}
async function sendUrl(){const u=$('send-url').value.trim();if(!u){toast('请输入URL');return}try{const r=await fetch('/api/epd_display/display_url',{method:'POST',headers:authH(),body:JSON.stringify({image_url:u,canvas:$('send-url-canvas').value,dither_mode:$('send-url-dither').value})});if(r.ok)toast('✅ 发送成功');else{const j=await r.json();toast('❌ '+j.error)}}catch(e){toast('❌ '+e.message)}}

// ══════ Editor State ══════
let cW=800,cH=480,bgColor='#ffffff',bgImg=null,bgImgPath='';
let elements=[],selIdx=-1,curTool='select';
let drawing=false,dragging=false,resizing=false;
let startX=0,startY=0,dragOffX=0,dragOffY=0,resizeHandle='';
const canvas=$('editor-canvas'),ctx=canvas.getContext('2d');

function applyCanvas(){cW=parseInt($('cw').value)||800;cH=parseInt($('ch').value)||480;canvas.width=cW;canvas.height=cH;$('canvas-info').textContent=`${cW} × ${cH}`;redraw()}
$('preset').addEventListener('change',function(){if(!this.value)return;const[w,h]=this.value.split(',').map(Number);$('cw').value=w;$('ch').value=h;applyCanvas()});
$('bg-color').addEventListener('input',function(){bgColor=this.value;redraw()});
$('bg-file').addEventListener('change',function(e){const f=e.target.files[0];if(!f)return;bgImgPath=f.name;const img=new Image();img.onload=()=>{bgImg=img;redraw()};img.src=URL.createObjectURL(f)});
function clearBg(){bgImg=null;bgImgPath='';$('bg-file').value='';const row=$('bg-path-row');if(row)row.style.display='none';redraw()}

function setTool(t){curTool=t;document.querySelectorAll('.tools .btn').forEach(b=>b.classList.toggle('on',b.dataset.tool===t));$('fill-row').style.display=t==='rectangle'?'flex':'none';$('text-opts').style.display=t==='text'?'block':'none';$('point-opts').style.display=t==='point'?'block':'none';$('computed-opts').style.display=t==='computed'?'block':'none';$('textbox-opts').style.display=t==='textbox'?'block':'none';$('calendar-opts').style.display=t==='calendar'?'block':'none';$('image-opts').style.display=t==='image'?'block':'none';canvas.style.cursor=t==='select'?'default':'crosshair'}
setTool('select');

// ── Hit/bounds ──
function getBounds(el){
  if(el.type==='rectangle')return{x:el.x,y:el.y,w:el.width,h:el.height};
  if(el.type==='line'){const p=el.points;return{x:Math.min(p[0],p[2]),y:Math.min(p[1],p[3]),w:Math.abs(p[2]-p[0])||4,h:Math.abs(p[3]-p[1])||4}}
  if(el.type==='point')return{x:el.x-el.radius,y:el.y-el.radius,w:el.radius*2,h:el.radius*2};
  if(el.type==='calendar')return{x:el.x,y:el.y,w:el.width||380,h:el.height||280};
  if(el.type==='image'){const iw=el.width||64,ih=el.height||64;return{x:el.x,y:el.y,w:iw,h:ih};}
  if(el.type==='computed_text'&&el.width&&el.height)return{x:el.x,y:el.y,w:el.width,h:el.height};
  if(el.type==='textbox'||el.type==='textbox_entity'||el.type==='textbox_computed')return{x:el.x,y:el.y,w:el.width||120,h:el.height||60};
  ctx.save();ctx.font=`${el.font_size||20}px sans-serif`;
  let t=el.text||'';
  if(el.type==='entity_text')t=(el.prefix||'')+(el._state||'{'+el.entity_id+'}')+(el.suffix||'');
  if(el.type==='computed_text')t=el._rendered||el.template||'{}';
  const m=ctx.measureText(t);ctx.restore();
  return{x:el.x,y:el.y,w:m.width||60,h:(el.font_size||20)*1.2};
}
function hitTest(mx,my){for(let i=elements.length-1;i>=0;i--){const b=getBounds(elements[i]);if(mx>=b.x-5&&mx<=b.x+b.w+5&&my>=b.y-5&&my<=b.y+b.h+5)return i}return-1}
function getResizeHandle(el,mx,my){const b=getBounds(el),hs=6;for(const c of[{n:'nw',cx:b.x,cy:b.y},{n:'ne',cx:b.x+b.w,cy:b.y},{n:'sw',cx:b.x,cy:b.y+b.h},{n:'se',cx:b.x+b.w,cy:b.y+b.h}])if(Math.abs(mx-c.cx)<=hs&&Math.abs(my-c.cy)<=hs)return c.n;return''}
function canvasPos(e){const r=canvas.getBoundingClientRect();return{x:Math.round((e.clientX-r.left)*cW/r.width),y:Math.round((e.clientY-r.top)*cH/r.height)}}

// ── Mouse ──
canvas.addEventListener('mousedown',e=>{const p=canvasPos(e);startX=p.x;startY=p.y;
  if(curTool==='select'){if(selIdx>=0){const h=getResizeHandle(elements[selIdx],p.x,p.y);if(h){resizing=true;resizeHandle=h;return}}const hit=hitTest(p.x,p.y);if(hit>=0){selIdx=hit;dragging=true;const b=getBounds(elements[hit]);dragOffX=p.x-b.x;dragOffY=p.y-b.y;refreshList();showProps(selIdx);redraw()}else{selIdx=-1;refreshList();hideProps();redraw()}return}
  if(curTool==='point'){elements.push({type:'point',x:p.x,y:p.y,radius:parseInt($('point-r').value)||4,color:$('draw-color').value});selIdx=elements.length-1;refreshList();redraw();return}
  if(curTool==='text'){elements.push({type:'text',x:p.x,y:p.y,text:$('text-input').value||'Text',color:$('draw-color').value,font_size:parseInt($('font-size').value)||24,font_path:''});selIdx=elements.length-1;refreshList();redraw();return}
  if(curTool==='computed'){const tpl=$('comp-tpl').value||'{{ now() }}';
    const iw=parseInt($('comp-iw').value)||null,ih=parseInt($('comp-ih').value)||null;
    const el={type:'computed_text',x:p.x,y:p.y,template:tpl,color:$('draw-color').value,font_size:parseInt($('comp-fs').value)||20,font_path:'',_rendered:'{...}'};
    if(iw)el.width=iw;if(ih)el.height=ih;
    elements.push(el);selIdx=elements.length-1;refreshList();redraw();return}
  if(curTool==='calendar'){
    const entsRaw=$('cal-entities').value.trim();
    const ents=entsRaw?entsRaw.split(',').map(s=>s.trim()).filter(Boolean):[];
    const yr=parseInt($('cal-year').value)||null;
    const mo=parseInt($('cal-month').value)||null;
    elements.push({type:'calendar',x:p.x,y:p.y,width:parseInt($('cal-w').value)||380,height:parseInt($('cal-h').value)||280,lang:$('cal-lang').value,first_weekday:parseInt($('cal-fwd').value)||0,year:yr,month:mo,calendar_entities:ents,show_event_text:true,max_events_per_cell:2,_preview_events:[]});
    selIdx=elements.length-1;refreshList();redraw();return}
  if(curTool==='image'){
    const path=$('img-path').value.trim();
    const iw=parseInt($('img-w').value)||64, ih=parseInt($('img-h').value)||64;
    const el={type:'image',x:p.x,y:p.y,
      path: _imgToolSvgContent ? '' : path,
      svg_content: _imgToolSvgContent || '',
      width:iw, height:ih,
      opacity:parseFloat($('img-opacity').value)||1,
      keep_aspect:$('img-aspect').checked,
      _img_obj:null};
    // 画布预览
    if(_imgToolSvgContent){
      const blob=new Blob([_imgToolSvgContent],{type:'image/svg+xml'});
      const url=URL.createObjectURL(blob);
      const im=new Image();im.crossOrigin='anonymous';
      im.onload=()=>{el._img_obj=im;redraw()};im.src=url;
    } else if(path){
      const previewUrl=imgPathToPreviewUrl(path);
      if(previewUrl){const im=new Image();im.crossOrigin='anonymous';im.onload=()=>{el._img_obj=im;redraw()};im.src=previewUrl;}
    }
    elements.push(el);selIdx=elements.length-1;refreshList();redraw();return}
  if(curTool==='textbox'){drawing=true;return}
  drawing=true});

canvas.addEventListener('mousemove',e=>{const p=canvasPos(e);$('coords').textContent=`X: ${p.x}  Y: ${p.y}`;
  if(curTool==='select'&&selIdx>=0&&!dragging&&!resizing){const h=getResizeHandle(elements[selIdx],p.x,p.y);canvas.style.cursor=h?({nw:'nwse-resize',ne:'nesw-resize',sw:'nesw-resize',se:'nwse-resize'}[h]):(hitTest(p.x,p.y)>=0?'move':'default')}
  if(dragging&&selIdx>=0){const el=elements[selIdx],nx=p.x-dragOffX,ny=p.y-dragOffY;if(el.type==='rectangle'){el.x=nx;el.y=ny}else if(el.type==='line'){const dx=nx-Math.min(el.points[0],el.points[2]),dy=ny-Math.min(el.points[1],el.points[3]);el.points=[el.points[0]+dx,el.points[1]+dy,el.points[2]+dx,el.points[3]+dy]}else if(el.type==='point'){el.x=nx+el.radius;el.y=ny+el.radius}else{el.x=nx;el.y=ny}redraw();return}
  if(resizing&&selIdx>=0){const el=elements[selIdx];if(el.type==='rectangle'){if(resizeHandle.includes('e'))el.width=Math.max(4,p.x-el.x);if(resizeHandle.includes('s'))el.height=Math.max(4,p.y-el.y);if(resizeHandle.includes('w')){const r=el.x+el.width;el.x=Math.min(p.x,r-4);el.width=r-el.x}if(resizeHandle.includes('n')){const b=el.y+el.height;el.y=Math.min(p.y,b-4);el.height=b-el.y}}else if(el.type==='line'){if(resizeHandle==='nw'||resizeHandle==='sw'){el.points[0]=p.x;el.points[1]=p.y}else{el.points[2]=p.x;el.points[3]=p.y}}else if(el.type==='point'){el.radius=Math.max(2,Math.round(Math.hypot(p.x-el.x,p.y-el.y)))}else if(el.type==='textbox'||el.type==='textbox_entity'||el.type==='textbox_computed'||el.type==='calendar'||el.type==='image'){if(resizeHandle.includes('e'))el.width=Math.max(8,p.x-el.x);if(resizeHandle.includes('s'))el.height=Math.max(8,p.y-el.y);if(resizeHandle.includes('w')){const r=el.x+el.width;el.x=Math.min(p.x,r-8);el.width=r-el.x}if(resizeHandle.includes('n')){const b=el.y+el.height;el.y=Math.min(p.y,b-8);el.height=b-el.y}}else{el.font_size=Math.max(6,Math.round(Math.abs(p.y-el.y)*1.2))}redraw();return}
  if(!drawing)return;redraw();ctx.save();ctx.strokeStyle=$('draw-color').value;ctx.lineWidth=parseInt($('draw-lw').value)||2;ctx.setLineDash([4,4]);if(curTool==='rectangle'||curTool==='textbox')ctx.strokeRect(startX,startY,p.x-startX,p.y-startY);else if(curTool==='line'){ctx.beginPath();ctx.moveTo(startX,startY);ctx.lineTo(p.x,p.y);ctx.stroke()}ctx.restore()});

canvas.addEventListener('mouseup',e=>{if(dragging){dragging=false;refreshList();showProps(selIdx);return}if(resizing){resizing=false;refreshList();showProps(selIdx);return}if(!drawing)return;drawing=false;const p=canvasPos(e),c=$('draw-color').value,lw=parseInt($('draw-lw').value)||2;
  if(curTool==='rectangle'){const x=Math.min(startX,p.x),y=Math.min(startY,p.y),w=Math.abs(p.x-startX),h=Math.abs(p.y-startY);if(w<2&&h<2)return;elements.push({type:'rectangle',x,y,width:w,height:h,outline:c,fill:$('fill-on').checked?$('fill-color').value:'',line_width:lw})}
  else if(curTool==='line'){if(Math.hypot(p.x-startX,p.y-startY)<2)return;elements.push({type:'line',points:[startX,startY,p.x,p.y],color:c,line_width:lw})}
  else if(curTool==='textbox'){
    const bx=Math.min(startX,p.x),by=Math.min(startY,p.y),bw=Math.abs(p.x-startX),bh=Math.abs(p.y-startY);
    if(bw<8&&bh<8)return;
    const tbMode=_tbMode||'static';
    const base={x:bx,y:by,width:bw,height:bh,
      color:$('draw-color').value,font_size:parseInt($('tb-fs').value)||20,
      padding:parseInt($('tb-pad').value)||6,
      line_spacing:parseInt($('tb-lsp').value)||2,
      align:$('tb-align').value||'left',
      valign:$('tb-valign').value||'top',
      bg_color:$('tb-bg-on').checked?$('tb-bg').value:'',
      border_color:$('tb-border-on').checked?$('tb-border').value:'',
      border_width:1, clip:true, font_path:''};
    let el;
    if(tbMode==='entity'){
      el={...base,type:'textbox_entity',entity_id:$('tb-eid').value||'',prefix:$('tb-pfx').value||'',suffix:$('tb-sfx').value||'',_state:''};
    } else if(tbMode==='computed'){
      el={...base,type:'textbox_computed',template:$('tb-tpl').value||'',_rendered:'{...}'};
    } else {
      el={...base,type:'textbox',text:($('tb-text').value||'示例文字').replace(/\n/g,'\n')};
    }
    elements.push(el);
  }
  selIdx=elements.length-1;refreshList();redraw()});

// ── Redraw ──
function redraw(){ctx.fillStyle=bgColor;ctx.fillRect(0,0,cW,cH);if(bgImg)ctx.drawImage(bgImg,0,0,cW,cH);
  elements.forEach((el,i)=>{ctx.save();
    if(el.type==='rectangle'){if(el.fill){ctx.fillStyle=el.fill;ctx.fillRect(el.x,el.y,el.width,el.height)}ctx.strokeStyle=el.outline||'#000';ctx.lineWidth=el.line_width||1;ctx.strokeRect(el.x,el.y,el.width,el.height)}
    else if(el.type==='line'){ctx.strokeStyle=el.color||'#000';ctx.lineWidth=el.line_width||1;ctx.beginPath();ctx.moveTo(el.points[0],el.points[1]);for(let j=2;j<el.points.length;j+=2)ctx.lineTo(el.points[j],el.points[j+1]);ctx.stroke()}
    else if(el.type==='point'){ctx.fillStyle=el.color||'#000';ctx.beginPath();ctx.arc(el.x,el.y,el.radius||3,0,Math.PI*2);ctx.fill()}
    else if(el.type==='text'){ctx.fillStyle=el.color||'#000';ctx.font=`${el.font_size||20}px sans-serif`;ctx.textBaseline='top';ctx.fillText(el.text,el.x,el.y)}
    else if(el.type==='entity_text'){ctx.fillStyle=el.color||'#000';ctx.font=`${el.font_size||20}px sans-serif`;ctx.textBaseline='top';ctx.fillText((el.prefix||'')+(el._state||'{'+el.entity_id+'}')+(el.suffix||''),el.x,el.y)}
    else if(el.type==='computed_text'){
      const rendered=el._rendered||'{'+el.template?.substring(0,20)+'}';
      const isImgPath=/^\/.*\.(png|jpg|jpeg|bmp|gif|webp|svg)$/i.test(rendered.trim());
      const isSvgContent=rendered.trim().startsWith('<svg')||rendered.trim().startsWith('<?xml');
      const showAsImg=isImgPath||isSvgContent;
      if(showAsImg&&el._img_obj){
        ctx.globalAlpha=el.opacity??1;
        ctx.drawImage(el._img_obj,el.x,el.y,el.width||el._img_obj.naturalWidth,el.height||el._img_obj.naturalHeight);
        ctx.globalAlpha=1;
      }else if(showAsImg){
        // 占位框
        const iw=el.width||48,ih=el.height||48;
        ctx.strokeStyle='#4895ef';ctx.lineWidth=1;ctx.setLineDash([3,3]);
        ctx.strokeRect(el.x,el.y,iw,ih);ctx.setLineDash([]);
        ctx.fillStyle='rgba(72,149,239,.1)';ctx.fillRect(el.x,el.y,iw,ih);
        ctx.fillStyle='#4895ef';ctx.font=`${Math.min(iw,ih)*0.4}px sans-serif`;
        ctx.textAlign='center';ctx.textBaseline='middle';
        ctx.fillText(isSvgContent?'SVG':'🖼',el.x+iw/2,el.y+ih/2);
        ctx.textAlign='left';ctx.textBaseline='top';
      }else{
        ctx.fillStyle=el.color||'#4895ef';ctx.font=`${el.font_size||20}px sans-serif`;ctx.textBaseline='top';
        ctx.fillText(rendered,el.x,el.y);
      }
    }
    else if(el.type==='textbox'||el.type==='textbox_entity'||el.type==='textbox_computed'){
      const tbx=el.x,tby=el.y,tbw=el.width||120,tbh=el.height||60;
      // 背景
      if(el.bg_color){ctx.fillStyle=el.bg_color;ctx.fillRect(tbx,tby,tbw,tbh);}
      // 边框
      if(el.border_color){ctx.strokeStyle=el.border_color;ctx.lineWidth=el.border_width||1;ctx.strokeRect(tbx,tby,tbw,tbh);}
      // 无背景时显示虚框提示
      if(!el.bg_color&&!el.border_color){ctx.strokeStyle='rgba(124,61,143,0.45)';ctx.lineWidth=1;ctx.setLineDash([4,3]);ctx.strokeRect(tbx,tby,tbw,tbh);ctx.setLineDash([]);}
      // 获取文本
      let tbText='';
      if(el.type==='textbox')tbText=el.text||'';
      else if(el.type==='textbox_entity')tbText=(el.prefix||'')+(el._state||'{'+el.entity_id+'}')+(el.suffix||'');
      else tbText=el._rendered||'{'+( el.template||'').substring(0,20)+'}';
      // 自动换行绘制
      const tbFs=el.font_size||20;const tbPad=el.padding||4;const tbLsp=el.line_spacing||2;
      ctx.font=`${tbFs}px sans-serif`;ctx.fillStyle=el.color||'#000';ctx.textBaseline='top';
      const tbInnerW=tbw-tbPad*2,tbInnerH=tbh-tbPad*2;
      if(tbInnerW>0&&tbText){
        // wrap
        const tbLines=[];
        for(const para of tbText.split('\n')){
          if(!para){tbLines.push('');continue;}
          let cur='';
          for(const ch of para){
            if(ctx.measureText(cur+ch).width<=tbInnerW)cur+=ch;
            else{if(cur)tbLines.push(cur);cur=ch;}
          }
          if(cur)tbLines.push(cur);
        }
        const tbStep=tbFs+tbLsp;
        const tbMaxLines=Math.max(1,Math.floor(tbInnerH/tbStep));
        const showLines=tbLines.slice(0,tbMaxLines);
        const totalH=showLines.length*tbStep-tbLsp;
        let curY;
        if(el.valign==='middle')curY=tby+tbPad+Math.max(0,(tbInnerH-totalH)/2);
        else if(el.valign==='bottom')curY=tby+tbPad+Math.max(0,tbInnerH-totalH);
        else curY=tby+tbPad;
        for(const ln of showLines){
          if(curY>tby+tbh-tbPad)break;
          const lw=ctx.measureText(ln).width;
          let lx;
          if(el.align==='center')lx=tbx+tbPad+Math.max(0,(tbInnerW-lw)/2);
          else if(el.align==='right')lx=tbx+tbPad+Math.max(0,tbInnerW-lw);
          else lx=tbx+tbPad;
          ctx.fillText(ln,lx,curY);curY+=tbStep;
        }
      }
    }
    else if(el.type==='calendar'){_drawCalendarPreview(ctx,el)}
    else if(el.type==='image'){
      const iw=el.width||64,ih=el.height||64;
      if(el._img_obj){
        ctx.globalAlpha=el.opacity??1;
        ctx.drawImage(el._img_obj,el.x,el.y,iw,ih);
        ctx.globalAlpha=1;
      }else{
        // 占位框：虚线矩形 + 图片图标
        ctx.strokeStyle='#2b6cb0';ctx.lineWidth=1.5;ctx.setLineDash([4,3]);
        ctx.strokeRect(el.x,el.y,iw,ih);ctx.setLineDash([]);
        ctx.fillStyle='rgba(43,108,176,.12)';ctx.fillRect(el.x,el.y,iw,ih);
        ctx.fillStyle='#5a9fd4';ctx.font=`${Math.min(iw,ih)*0.4}px sans-serif`;
        ctx.textAlign='center';ctx.textBaseline='middle';
        ctx.fillText('🖼',el.x+iw/2,el.y+ih/2);
        ctx.textAlign='left';ctx.textBaseline='top';
        if(el.path){ctx.font='9px sans-serif';ctx.fillStyle='#5a9fd4';
          const name=el.path.split('/').pop();
          ctx.fillText(name.substring(0,12),el.x+2,el.y+ih-12);}
      }
    }
    if(i===selIdx){const b=getBounds(el);ctx.strokeStyle='rgba(34,211,167,.85)';ctx.lineWidth=1;ctx.setLineDash([3,3]);ctx.strokeRect(b.x-3,b.y-3,b.w+6,b.h+6);ctx.setLineDash([]);ctx.fillStyle='#22d3a7';[[b.x,b.y],[b.x+b.w,b.y],[b.x,b.y+b.h],[b.x+b.w,b.y+b.h]].forEach(([hx,hy])=>ctx.fillRect(hx-4,hy-4,8,8))}
    ctx.restore()})}

// ── Element list ──
function refreshList(){const list=$('el-list');$('el-count').textContent=`(${elements.length})`;list.innerHTML='';
  elements.forEach((el,i)=>{const d=document.createElement('div');d.className='el-item'+(i===selIdx?' sel':'');
    const bc=el.type==='entity_text'?'entity':el.type==='computed_text'?'computed':el.type==='rectangle'?'rect':el.type==='calendar'?'calendar':el.type==='image'?'image':(el.type==='textbox'||el.type==='textbox_entity'||el.type==='textbox_computed')?'textbox':el.type;
    const label=el.type==='entity_text'?'实体':el.type==='computed_text'?'代码':el.type==='calendar'?'日历':el.type==='image'?'图标':el.type==='textbox'?'文本框':el.type==='textbox_entity'?'框-实体':el.type==='textbox_computed'?'框-代码':el.type;
    let info='';
    if(el.type==='rectangle')info=`${el.x},${el.y} ${el.width}×${el.height}`;
    else if(el.type==='line')info=`(${el.points[0]},${el.points[1]})→(${el.points[2]},${el.points[3]})`;
    else if(el.type==='point')info=`(${el.x},${el.y}) r=${el.radius}`;
    else if(el.type==='text')info=`"${el.text}" @${el.x},${el.y}`;
    else if(el.type==='entity_text')info=`${el.entity_id}`;
    else if(el.type==='computed_text')info=el.template?.substring(0,30)||'';
    else if(el.type==='calendar'){const ym=(el.year||'??')+'/'+(el.month||'??');info=`${ym} ${el.width||380}×${el.height||280} ${(el.calendar_entities||[]).length}实体`;}
    else if(el.type==='image'){const name=(el.path||'').split('/').pop()||'未设置';info=`${name} ${el.width||64}×${el.height||64}`;}
    else if(el.type==='textbox')info=`"${(el.text||'').substring(0,18)}" ${el.width||120}×${el.height||60}`;
    else if(el.type==='textbox_entity')info=`${el.entity_id||'?'} ${el.width||120}×${el.height||60}`;
    else if(el.type==='textbox_computed')info=`${(el.template||'').substring(0,20)} ${el.width||120}×${el.height||60}`;
    d.innerHTML=`<span class="badge ${bc}">${label}</span><span class="info">${info}</span><button class="x-btn" data-action="delElem" data-arg="${i}">×</button>`;
    d.addEventListener('click',()=>{selIdx=i;refreshList();showProps(i);redraw()});list.appendChild(d)});
  if(selIdx>=0&&selIdx<elements.length)showProps(selIdx);else hideProps()}

// ── Props ──
function showProps(idx){const el=elements[idx];if(!el){hideProps();return}$('props-sec').style.display='block';const p=$('props-panel');
  const R=(l,id,v,t='text')=>`<div class="row"><label>${l}</label><input type="${t}" id="p-${id}" value="${v??''}" style="flex:1"></div>`;
  let h='';
  if(el.type==='rectangle'){h+=R('X','x',el.x,'number')+R('Y','y',el.y,'number')+R('宽','w',el.width,'number')+R('高','h',el.height,'number')+R('边框','ol',el.outline||'#000','color')+R('填充','fl',el.fill||'#fff','color')+R('线宽','lw',el.line_width||1,'number')}
  else if(el.type==='line'){h+=R('X1','x1',el.points[0],'number')+R('Y1','y1',el.points[1],'number')+R('X2','x2',el.points[2],'number')+R('Y2','y2',el.points[3],'number')+R('颜色','c',el.color||'#000','color')+R('线宽','lw',el.line_width||1,'number')}
  else if(el.type==='point'){h+=R('X','x',el.x,'number')+R('Y','y',el.y,'number')+R('半径','r',el.radius||3,'number')+R('颜色','c',el.color||'#000','color')}
  else if(el.type==='text'){h+=R('X','x',el.x,'number')+R('Y','y',el.y,'number')+R('文字','txt',el.text)+R('颜色','c',el.color||'#000','color')+R('字号','fs',el.font_size||20,'number')}
  else if(el.type==='entity_text'){h+=R('X','x',el.x,'number')+R('Y','y',el.y,'number')+R('实体','eid',el.entity_id)+R('前缀','pfx',el.prefix||'')+R('后缀','sfx',el.suffix||'')+R('颜色','c',el.color||'#000','color')+R('字号','fs',el.font_size||20,'number');h+=`<button class="btn btn-s btn-sm" style="margin-top:3px" data-action="pickEntityForProp">🔍 选择</button> <button class="btn btn-s btn-sm" data-action="refreshEntityState">🔄 刷新</button>`}
  else if(el.type==='computed_text'){h+=R('X','x',el.x,'number')+R('Y','y',el.y,'number')+R('颜色','c',el.color||'#4895ef','color')+R('字号','fs',el.font_size||20,'number');h+=R('图标宽','ciw',el.width||'','number')+R('图标高','cih',el.height||'','number');h+=`<div style="margin-top:4px"><div style="font-size:10px;color:var(--text2)">Jinja2 模板（输出文字 或 /路径/图标.svg|.png）:</div><textarea id="p-tpl" style="width:100%;height:60px;background:var(--bg);color:#a6e3a1;font-family:var(--mono);font-size:11px;border:1px solid var(--bd);border-radius:var(--r);padding:5px;resize:vertical;outline:none">${el.template||''}</textarea></div>`;h+=`<button class="btn btn-s btn-sm" style="margin-top:3px" data-action="previewComputed">▶ 预览</button>`}
  else if(el.type==='image'){
    h+=R('X','x',el.x,'number')+R('Y','y',el.y,'number')+R('宽','iw',el.width||64,'number')+R('高','ih',el.height||64,'number');
    h+=R('透明度','opacity',el.opacity??1,'number');
    h+=`<div class="row"><label>保持比</label><label style="width:auto"><input type="checkbox" id="p-aspect"${el.keep_aspect!==false?' checked':''}> 开启</label></div>`;
    if(el.svg_content){
      h+=`<div style="font-size:10px;color:var(--ac);margin:5px 0 2px">✅ SVG 内容已嵌入（${Math.round(el.svg_content.length/1024*10)/10}KB）</div>`;
      h+=`<div class="btn-group" style="margin-top:3px">
        <button class="btn btn-s btn-sm" data-action="pSvgLocalClick">🔄 重新选择文件</button>
        <button class="btn btn-d btn-sm" data-action="clearPropSvgContent">× 清除</button>
      </div>`;
    } else {
      h+=`<div style="font-size:10px;color:var(--text2);margin:5px 0 2px">SVG/图片来源:</div>`;
      h+=`<div class="btn-group" style="margin-top:3px">
        <button class="btn btn-s btn-sm" data-action="pSvgLocalClick">📁 本地SVG</button>
        <button class="btn btn-s btn-sm" data-action="openImgPickerForProp">📂 从HA选择</button>
      </div>`;
      h+=`<div style="font-size:10px;color:var(--text2);margin:4px 0 2px">或服务器路径:</div>`;
      h+=`<div style="display:flex;gap:4px"><input type="text" id="p-imgpath" value="${el.path||''}" style="flex:1;background:var(--bg);border:1px solid var(--bd);color:var(--text);padding:4px 6px;border-radius:var(--r);font-size:10px;outline:none"></div>`;
      h+=`<button class="btn btn-s btn-sm" style="margin-top:4px" data-action="reloadImgPreview">🔄 重载预览</button>`;
    }
    h+=`<input type="file" id="p-svg-local" accept="image/*,.svg" class="hidden-input">`;
    if(el._img_obj)h+=`<div style="margin-top:6px"><img src="${el._img_obj.src}" style="max-width:100%;max-height:80px;border-radius:3px;border:1px solid var(--bd)"></div>`;
    else if(el.path&&!el.svg_content)h+=`<div style="font-size:10px;color:var(--warn);margin-top:4px">⚠ 预览未加载</div>`;
  }
  else if(el.type==='textbox'||el.type==='textbox_entity'||el.type==='textbox_computed'){
    // ── 切换内容类型 ──
    const tbTypes=[['textbox','静态文字'],['textbox_entity','传感器'],['textbox_computed','Jinja2代码']];
    h+=`<div style="margin-bottom:6px"><div style="font-size:10px;color:var(--text2);margin-bottom:3px">内容类型</div><div class="btn-group">`;
    tbTypes.forEach(([t,label])=>{
      const on=el.type===t;
      h+=`<button class="btn btn-sm ${on?'btn-a':'btn-s'}" data-action="switchTbType" data-arg="${t}">${label}</button>`;
    });
    h+=`</div></div>`;
    // ── 位置尺寸 ──
    h+=R('X','x',el.x,'number')+R('Y','y',el.y,'number')+R('宽','tbw',el.width||120,'number')+R('高','tbh',el.height||60,'number');
    // ── 字体样式 ──
    h+=R('字号','tbfs',el.font_size||20,'number')+R('内边距','tbpad',el.padding||4,'number')+R('行间距','tblsp',el.line_spacing||2,'number');
    h+=R('文字色','c',el.color||'#000','color');
    h+=`<div class="row"><label>对齐</label><select id="p-tbalign" style="flex:1;background:var(--bg);border:1px solid var(--bd);color:var(--text);padding:4px 6px;border-radius:var(--r);font-size:11px"><option value="left"${el.align==='left'?' selected':''}>左对齐</option><option value="center"${el.align==='center'?' selected':''}>居中</option><option value="right"${el.align==='right'?' selected':''}>右对齐</option></select></div>`;
    h+=`<div class="row"><label>垂直</label><select id="p-tbvalign" style="flex:1;background:var(--bg);border:1px solid var(--bd);color:var(--text);padding:4px 6px;border-radius:var(--r);font-size:11px"><option value="top"${el.valign==='top'?' selected':''}>顶部</option><option value="middle"${el.valign==='middle'?' selected':''}>居中</option><option value="bottom"${el.valign==='bottom'?' selected':''}>底部</option></select></div>`;
    h+=`<div class="row"><label>背景色</label><input type="color" id="p-tbbg" value="${el.bg_color||'#ffffff'}"><label style="width:auto;font-size:10px;display:flex;align-items:center;gap:3px"><input type="checkbox" id="p-tbbg-on"${el.bg_color?' checked':''}> 启用</label></div>`;
    h+=`<div class="row"><label>边框色</label><input type="color" id="p-tbborder" value="${el.border_color||'#000000'}"><label style="width:auto;font-size:10px;display:flex;align-items:center;gap:3px"><input type="checkbox" id="p-tbborder-on"${el.border_color?' checked':''}> 启用</label></div>`;
    // ── 内容区（按类型显示）──
    h+=`<div style="border-top:1px solid var(--bd);margin:7px 0 5px"></div>`;
    if(el.type==='textbox'){
      h+=`<div style="font-size:10px;color:var(--text2);margin-bottom:3px">文字内容（\\n 换行）:</div>`;
      h+=`<textarea id="p-tbtext" style="width:100%;height:72px;background:var(--bg);color:var(--text);font-family:var(--mono);font-size:11px;border:1px solid var(--bd);border-radius:var(--r);padding:5px;resize:vertical;outline:none">${(el.text||'').replace(/</g,'&lt;')}</textarea>`;
    } else if(el.type==='textbox_entity'){
      h+=`<div style="font-size:10px;color:var(--text2);margin-bottom:3px">传感器实体:</div>`;
      h+=`<div style="display:flex;gap:4px;margin-bottom:4px"><input type="text" id="p-tbeid" value="${el.entity_id||''}" placeholder="sensor.xxx" style="flex:1;background:var(--bg);border:1px solid var(--bd);color:var(--text);padding:4px 6px;border-radius:var(--r);font-size:11px;outline:none"><button class="btn btn-s btn-sm" data-action="pickEntityForTbProp">🔍</button></div>`;
      h+=R('前缀','tbpfx',el.prefix||'')+R('后缀','tbsfx',el.suffix||'');
      const curState=el._state?`<span style="color:var(--ac)">${el._state}</span>`:`<span style="color:var(--text3)">未加载</span>`;
      h+=`<div style="font-size:10px;color:var(--text2);margin-top:4px">当前值: ${curState}</div>`;
      h+=`<button class="btn btn-s btn-sm" style="margin-top:5px" data-action="refreshTbEntityState">🔄 刷新状态</button>`;
    } else if(el.type==='textbox_computed'){
      h+=`<div style="font-size:10px;color:var(--text2);margin-bottom:3px">Jinja2 模板表达式:</div>`;
      h+=`<textarea id="p-tbtpl" style="width:100%;height:80px;background:var(--bg);color:#a6e3a1;font-family:var(--mono);font-size:11px;border:1px solid var(--bd);border-radius:var(--r);padding:5px;resize:vertical;outline:none">${(el.template||'').replace(/</g,'&lt;')}</textarea>`;
      const previewVal=el._rendered&&el._rendered!=='{...}'?`<span style="color:var(--ac)">${el._rendered}</span>`:`<span style="color:var(--text3)">点击预览</span>`;
      h+=`<div style="font-size:10px;color:var(--text2);margin-top:4px">预览结果: ${previewVal}</div>`;
      h+=`<button class="btn btn-a btn-sm" style="margin-top:5px" data-action="previewTbComputed">▶ 预览</button>`;
    }
  }
  else if(el.type==='calendar'){
    h+=R('X','x',el.x,'number')+R('Y','y',el.y,'number')+R('宽','cw',el.width||380,'number')+R('高','ch',el.height||280,'number');
    h+=R('年','year',el.year||'','number')+R('月','month',el.month||'','number');
    h+=`<div class="row"><label>语言</label><select id="p-lang" style="flex:1;background:var(--bg);border:1px solid var(--bd);color:var(--text);padding:4px 6px;border-radius:var(--r);font-size:11px"><option value="zh"${el.lang==='zh'?' selected':''}>中文</option><option value="en"${el.lang==='en'?' selected':''}>English</option></select></div>`;
    h+=`<div class="row"><label>周首日</label><select id="p-fwd" style="flex:1;background:var(--bg);border:1px solid var(--bd);color:var(--text);padding:4px 6px;border-radius:var(--r);font-size:11px"><option value="0"${el.first_weekday===0?' selected':''}>周一</option><option value="6"${el.first_weekday===6?' selected':''}>周日</option></select></div>`;
    h+=`<div style="font-size:10px;color:var(--text2);margin:4px 0">日历实体（逗号分隔）:</div><input type="text" id="p-cal-ents" value="${(el.calendar_entities||[]).join(', ')}" style="width:100%;background:var(--bg);border:1px solid var(--bd);color:var(--text);padding:4px 6px;border-radius:var(--r);font-size:11px;outline:none;margin-bottom:4px">`;
    h+=`<div class="btn-group"><button class="btn btn-s btn-sm" data-action="pickCalEntityForProp">🔍 选实体</button><button class="btn btn-s btn-sm" data-action="fetchCalPreviewForProp">🔄 获取事件</button></div>`;
    if(el._preview_events&&el._preview_events.length)h+=`<div style="font-size:10px;color:var(--ac);margin-top:4px">已加载 ${el._preview_events.length} 条事件</div>`;
  }
  p.innerHTML=h}
function hideProps(){$('props-sec').style.display='none'}
function applyProps(){if(selIdx<0)return;const el=elements[selIdx],g=id=>{const i=$('p-'+id);return i?i.value:''},gn=id=>parseInt(g(id))||0;
  if(el.type==='rectangle'){el.x=gn('x');el.y=gn('y');el.width=gn('w');el.height=gn('h');el.outline=g('ol');el.fill=g('fl');el.line_width=gn('lw')}
  else if(el.type==='line'){el.points=[gn('x1'),gn('y1'),gn('x2'),gn('y2')];el.color=g('c');el.line_width=gn('lw')}
  else if(el.type==='point'){el.x=gn('x');el.y=gn('y');el.radius=gn('r');el.color=g('c')}
  else if(el.type==='text'){el.x=gn('x');el.y=gn('y');el.text=g('txt');el.color=g('c');el.font_size=gn('fs')}
  else if(el.type==='entity_text'){el.x=gn('x');el.y=gn('y');el.entity_id=g('eid');el.prefix=g('pfx');el.suffix=g('sfx');el.color=g('c');el.font_size=gn('fs')}
  else if(el.type==='computed_text'){el.x=gn('x');el.y=gn('y');el.color=g('c');el.font_size=gn('fs');
    const ciw=gn('ciw'),cih=gn('cih');if(ciw)el.width=ciw;else delete el.width;if(cih)el.height=cih;else delete el.height;
    const tpl=$('p-tpl');if(tpl)el.template=tpl.value}
  else if(el.type==='image'){
    el.x=gn('x');el.y=gn('y');el.width=gn('iw')||64;el.height=gn('ih')||64;
    el.opacity=parseFloat(g('opacity'))||1;
    const asp=$('p-aspect');if(asp)el.keep_aspect=asp.checked;
    const pp=$('p-imgpath');if(pp&&pp.value.trim()!==el.path){el.path=pp.value.trim();el._img_obj=null;_loadImgObj(el);}
  }
  else if(el.type==='textbox'||el.type==='textbox_entity'||el.type==='textbox_computed'){
    el.x=gn('x');el.y=gn('y');el.width=gn('tbw')||120;el.height=gn('tbh')||60;
    el.font_size=gn('tbfs')||20;el.padding=gn('tbpad');el.line_spacing=gn('tblsp');
    el.color=g('c');
    const alignEl=$('p-tbalign');if(alignEl)el.align=alignEl.value;
    const valignEl=$('p-tbvalign');if(valignEl)el.valign=valignEl.value;
    const bgOn=$('p-tbbg-on');el.bg_color=(bgOn&&bgOn.checked)?g('tbbg'):'';
    const bdOn=$('p-tbborder-on');el.border_color=(bdOn&&bdOn.checked)?g('tbborder'):'';
    if(el.type==='textbox'){const ta=$('p-tbtext');if(ta)el.text=ta.value;}
    else if(el.type==='textbox_entity'){el.entity_id=g('tbeid');el.prefix=g('tbpfx');el.suffix=g('tbsfx');}
    else if(el.type==='textbox_computed'){const ta=$('p-tbtpl');if(ta)el.template=ta.value;}
  }
  else if(el.type==='calendar'){
    el.x=gn('x');el.y=gn('y');el.width=gn('cw')||380;el.height=gn('ch')||280;
    const yr=gn('year');el.year=yr||null;
    const mo=gn('month');el.month=mo||null;
    const langEl=$('p-lang');if(langEl)el.lang=langEl.value;
    const fwdEl=$('p-fwd');if(fwdEl)el.first_weekday=parseInt(fwdEl.value)||0;
    const entsEl=$('p-cal-ents');if(entsEl)el.calendar_entities=entsEl.value.split(',').map(s=>s.trim()).filter(Boolean);
  }
  refreshList();redraw()}

// 切换文本框内容类型（保留位置/尺寸/样式，只换 type 和内容字段）
function switchTbType(newType){
  if(selIdx<0)return;
  const el=elements[selIdx];
  if(!el||(el.type!=='textbox'&&el.type!=='textbox_entity'&&el.type!=='textbox_computed'))return;
  if(el.type===newType)return;
  // 先保存当前面板里的值
  const g=id=>{const i=document.getElementById('p-'+id);return i?i.value:''};
  const base={x:el.x,y:el.y,width:el.width,height:el.height,
    font_size:parseInt(g('tbfs'))||el.font_size||20,
    padding:parseInt(g('tbpad'))||el.padding||4,
    line_spacing:parseInt(g('tblsp'))||el.line_spacing||2,
    color:g('c')||el.color||'#000',
    align:(document.getElementById('p-tbalign')||{}).value||el.align||'left',
    valign:(document.getElementById('p-tbvalign')||{}).value||el.valign||'top',
    bg_color:(document.getElementById('p-tbbg-on')?.checked)?g('tbbg'):el.bg_color||'',
    border_color:(document.getElementById('p-tbborder-on')?.checked)?g('tbborder'):el.border_color||'',
  };
  // 按新类型建立内容字段
  if(newType==='textbox'){
    // 尽量保留旧内容
    const oldText=el.text||(el.type==='textbox_entity'?((el.prefix||'')+(el._state||el.entity_id||'')+(el.suffix||'')):el._rendered||'');
    elements[selIdx]={...base,type:'textbox',text:oldText};
  }else if(newType==='textbox_entity'){
    elements[selIdx]={...base,type:'textbox_entity',entity_id:el.entity_id||'',prefix:el.prefix||'',suffix:el.suffix||'',_state:el._state||''};
  }else if(newType==='textbox_computed'){
    elements[selIdx]={...base,type:'textbox_computed',template:el.template||'',_rendered:el._rendered||'{...}'};
  }
  refreshList();showProps(selIdx);redraw();
}

async function previewComputed(){if(selIdx<0)return;const el=elements[selIdx];if(el.type!=='computed_text')return;
  const tpl=$('p-tpl');if(tpl)el.template=tpl.value;
  try{const r=await fetch('/api/epd_display/template_preview',{method:'POST',headers:authH(),body:JSON.stringify({template:el.template})});const j=await r.json();if(r.ok){
    el._rendered=j.result;
    const trimmed=j.result.trim();
    const isImgPath=/^\/.*\.(png|jpg|jpeg|bmp|gif|webp|svg)$/i.test(trimmed);
    const isSvgContent=trimmed.startsWith('<svg')||trimmed.startsWith('<?xml');
    if(isSvgContent){
      // SVG 内容：用 Blob URL 在画布上预览
      el._img_obj=null;
      const blob=new Blob([trimmed],{type:'image/svg+xml'});
      const url=URL.createObjectURL(blob);
      const im=new Image();im.crossOrigin='anonymous';
      im.onload=()=>{el._img_obj=im;redraw();};im.src=url;
      toast('SVG内容预览已加载');
    }else if(isImgPath){
      el._img_obj=null;
      const url=imgPathToPreviewUrl(trimmed);
      if(url){const im=new Image();im.crossOrigin='anonymous';im.onload=()=>{el._img_obj=im;redraw()};im.src=url;}
      toast('图标路径: '+trimmed.split('/').pop());
    }else{el._img_obj=null;toast('预览: '+j.result);}
    redraw();
  }else toast('❌ '+j.error)}catch(e){toast('❌ '+e.message)}}

function delElem(i){elements.splice(i,1);if(selIdx>=elements.length)selIdx=elements.length-1;refreshList();redraw()}
function delSelected(){if(selIdx>=0)delElem(selIdx)}
function clearAll(){if(elements.length&&!confirm('清空？'))return;elements=[];selIdx=-1;refreshList();redraw()}

// ── Entities ──
let allEntities=[],entityPickCb=null;
async function loadEntities(){try{const r=await fetch('/api/epd_display/entities',{headers:authH()});if(r.ok)allEntities=await r.json()}catch(e){}}
loadEntities();
// ── Textbox tool helpers ──
let _tbMode='static';
function setTbMode(m){_tbMode=m;
  ['static','entity','computed'].forEach(n=>{
    $('tb-sub-'+n).style.display=n===m?'block':'none';
    $('tb-mode-'+n).classList.toggle('btn-a',n===m);
    $('tb-mode-'+n).classList.toggle('btn-s',n!==m);
  });}
function pickEntityForTb(){entityPickCb=(eid,state)=>{$('tb-eid').value=eid;};openEntityPicker()}
function pickEntityForTbProp(){entityPickCb=(eid,state)=>{
  const inp=$('p-tbeid');if(inp)inp.value=eid;
  if(selIdx>=0&&elements[selIdx]){elements[selIdx].entity_id=eid;elements[selIdx]._state=state;redraw();}
};openEntityPicker()}
async function refreshTbEntityState(){if(selIdx<0)return;const el=elements[selIdx];if(el.type!=='textbox_entity')return;
  await loadEntities();const f=allEntities.find(e=>e.entity_id===el.entity_id);el._state=f?f.state:'N/A';redraw();toast('已刷新')}
async function previewTbComputed(){if(selIdx<0)return;const el=elements[selIdx];if(el.type!=='textbox_computed')return;
  const ta=$('p-tbtpl');if(ta)el.template=ta.value;
  try{const r=await fetch('/api/epd_display/template_preview',{method:'POST',headers:authH(),body:JSON.stringify({template:el.template})});
    const j=await r.json();if(r.ok){el._rendered=j.result;redraw();toast('预览: '+j.result.substring(0,40))}else toast('❌ '+j.error)
  }catch(e){toast('❌ '+e.message)}}

function addEntityText(){entityPickCb=(eid,state)=>{elements.push({type:'entity_text',x:50,y:50,entity_id:eid,prefix:'',suffix:'',color:'#000000',font_size:24,font_path:'',_state:state});selIdx=elements.length-1;refreshList();redraw()};openEntityPicker()}
function pickEntityForProp(){entityPickCb=(eid,state)=>{const inp=$('p-eid');if(inp)inp.value=eid;if(selIdx>=0){elements[selIdx].entity_id=eid;elements[selIdx]._state=state}redraw()};openEntityPicker()}
async function refreshEntityState(){if(selIdx<0)return;const el=elements[selIdx];if(el.type!=='entity_text')return;await loadEntities();const f=allEntities.find(e=>e.entity_id===el.entity_id);el._state=f?f.state:'N/A';redraw();toast('已刷新')}
async function refreshAllStates(){await loadEntities();elements.forEach(el=>{if(el.type==='entity_text'||el.type==='textbox_entity'){const f=allEntities.find(e=>e.entity_id===el.entity_id);el._state=f?f.state:'N/A'}});redraw()}
function openEntityPicker(){$('entity-search').value='';renderEntityList('');$('entity-modal').classList.add('open');setTimeout(()=>$('entity-search').focus(),100)}
function filterEntities(){renderEntityList($('entity-search').value.toLowerCase())}
function renderEntityList(f){const c=$('entity-list-container');c.innerHTML='';allEntities.filter(e=>!f||e.entity_id.toLowerCase().includes(f)||(e.name||'').toLowerCase().includes(f)).slice(0,200).forEach(e=>{const d=document.createElement('div');d.className='entity-row';d.innerHTML=`<span class="eid">${e.entity_id}</span><span class="ename">${e.name||''}</span><span class="estate">${e.state}${e.unit?' '+e.unit:''}</span>`;d.addEventListener('click',()=>{closeModal('entity-modal');if(entityPickCb)entityPickCb(e.entity_id,e.state)});c.appendChild(d)})}

// ══════ Build data / YAML / JSON / PNG ══════
function buildData(){const d={width:cW,height:cH,background_color:bgColor};if(bgImgPath)d.background_image=bgImgPath;
  d.elements=elements.map(el=>{const o={...el};delete o._state;delete o._rendered;delete o._preview_events;delete o._img_obj;if(o.type==='rectangle'&&!o.fill)delete o.fill;if(o.font_path==='')delete o.font_path;return o});
  d.output_filename='epd_editor_output.png';return d}
function fmtVal(v){if(typeof v==='string'){if(!v||v.includes(':')||v.includes('#')||v.includes("'")||v.includes('{'))return`"${v.replace(/\\/g,'\\\\').replace(/"/g,'\\"')}"`;return v}if(Array.isArray(v))return'['+v.join(', ')+']';return String(v)}
function toYAML(obj,ind=0){const pad='  '.repeat(ind);let out='';if(Array.isArray(obj)){obj.forEach(item=>{if(typeof item==='object'&&item&&!Array.isArray(item)){const ks=Object.keys(item);out+=`${pad}- ${ks[0]}: ${fmtVal(item[ks[0]])}\n`;ks.slice(1).forEach(k=>out+=`${pad}  ${k}: ${fmtVal(item[k])}\n`)}else out+=`${pad}- ${fmtVal(item)}\n`})}else if(typeof obj==='object'&&obj){Object.keys(obj).forEach(k=>{const v=obj[k];if(Array.isArray(v))out+=`${pad}${k}:\n`+toYAML(v,ind+1);else if(typeof v==='object'&&v)out+=`${pad}${k}:\n`+toYAML(v,ind+1);else out+=`${pad}${k}: ${fmtVal(v)}\n`})}return out}
function openYaml(){$('yaml-out').value=`service: epd_display.generate_image\ndata:\n${toYAML(buildData(),1)}`;$('yaml-modal').classList.add('open')}
function exportJSON(){const b=new Blob([JSON.stringify({cW,cH,bgColor,bgImgPath,elements:JSON.parse(JSON.stringify(elements))},null,2)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='epd_project.json';a.click()}
function importJSON(){const inp=$('import-input');inp.onchange=e=>{const f=e.target.files[0];if(!f)return;const r=new FileReader();r.onload=ev=>{try{const d=JSON.parse(ev.target.result);cW=d.cW||800;cH=d.cH||480;bgColor=d.bgColor||'#fff';bgImgPath=d.bgImgPath||'';elements=d.elements||[];selIdx=-1;$('cw').value=cW;$('ch').value=cH;$('bg-color').value=bgColor;applyCanvas();refreshList();redraw();refreshAllStates();restoreImgObjs();toast('已导入')}catch(e){toast('错误: '+e.message)}};r.readAsText(f);inp.value=''};inp.click()}
function downloadPNG(){const sv=selIdx;selIdx=-1;redraw();canvas.toBlob(b=>{const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='epd_output.png';a.click();selIdx=sv;redraw()},'image/png')}

// ── HA API ──
async function generateOnHA(){await refreshAllStates();const d=buildData();try{const r=await fetch('/api/epd_display/generate',{method:'POST',headers:authH(),body:JSON.stringify(d)});const j=await r.json();if(r.ok)toast('✅ 已保存: '+j.path);else toast('❌ '+j.error)}catch(e){toast('❌ '+e.message)}}
async function generateAndSend(){await refreshAllStates();const d=buildData();try{const r1=await fetch('/api/epd_display/generate',{method:'POST',headers:authH(),body:JSON.stringify(d)});const j1=await r1.json();if(!r1.ok){toast('❌ '+j1.error);return}const r2=await fetch('/api/services/epd_display/display_image',{method:'POST',headers:authH(),body:JSON.stringify({image_path:j1.path,canvas:haConfig.defaults.canvas,dither_mode:haConfig.defaults.dither_mode})});if(r2.ok)toast('✅ 已发送！');else toast('❌ 发送失败')}catch(e){toast('❌ '+e.message)}}

// ══════ Template Management ══════
let tplList=[], selectedTpl='';
async function loadTemplateList(){try{const r=await fetch('/api/epd_display/templates',{headers:authH()});if(r.ok){const j=await r.json();tplList=j.templates||[]}}catch(e){}renderTplList()}
function renderTplList(){const c=$('tpl-list');c.innerHTML='';if(!tplList.length){c.innerHTML='<div style="padding:16px;text-align:center;color:var(--text3);font-size:12px">暂无模板</div>';return}
  tplList.forEach(n=>{const d=document.createElement('div');d.className='tpl-item'+(n===selectedTpl?' sel':'');d.innerHTML=`<span class="name">${n}</span><button class="del" data-action="deleteTpl" data-arg="${n}">×</button>`;d.addEventListener('click',()=>{selectedTpl=n;renderTplList();loadTplToEditor(n)});c.appendChild(d)})}

async function loadTplToEditor(name){try{const r=await fetch('/api/epd_display/templates/'+encodeURIComponent(name),{headers:authH()});if(r.ok){const d=await r.json();$('yaml-editor').value=toYAML(d);toast('已加载: '+name)}}catch(e){toast('❌ '+e.message)}}

function saveCurrentAsTemplate(){$('tpl-name-input').value='';$('tpl-name-modal').classList.add('open');window._tplSaveSource='editor'}
function yamlSaveAsTemplate(){$('tpl-name-input').value='';$('tpl-name-modal').classList.add('open');window._tplSaveSource='yaml'}

async function confirmSaveTemplate(){const name=$('tpl-name-input').value.trim();if(!name){toast('请输入名称');return}closeModal('tpl-name-modal');
  let data;
  if(window._tplSaveSource==='yaml'){try{data=await parseYamlViaAPI($('yaml-editor').value)}catch(e){toast('YAML解析错误: '+e.message);return}}
  else{data=buildData()}
  try{const r=await fetch('/api/epd_display/templates/'+encodeURIComponent(name),{method:'PUT',headers:authH(),body:JSON.stringify(data)});if(r.ok){toast('✅ 模板已保存: '+name);loadTemplateList()}else toast('❌ 保存失败')}catch(e){toast('❌ '+e.message)}}

async function deleteTpl(name){if(!confirm(`删除模板 "${name}"？`))return;try{await fetch('/api/epd_display/templates/'+encodeURIComponent(name),{method:'DELETE',headers:authH()});toast('已删除');if(selectedTpl===name)selectedTpl='';loadTemplateList()}catch(e){toast('❌ '+e.message)}}

// ── YAML code editor actions ──
// YAML 解析委托给后端 Python yaml.safe_load（支持所有合法 YAML 语法）
async function parseYamlViaAPI(text) {
  const r = await fetch('/api/epd_display/parse_yaml', {
    method: 'POST', headers: authH(),
    body: JSON.stringify({yaml: text})
  });
  const j = await r.json();
  if (!r.ok) throw new Error(j.error || 'YAML解析失败');
  return j.result;
}

async function yamlPreviewGenerate(){
  let data;try{data=await parseYamlViaAPI($('yaml-editor').value)}catch(e){$('yaml-preview').textContent='YAML错误: '+e.message;return}
  try{const r=await fetch('/api/epd_display/generate',{method:'POST',headers:authH(),body:JSON.stringify(data)});const j=await r.json();if(r.ok)$('yaml-preview').textContent='✅ 生成成功: '+j.path;else $('yaml-preview').textContent='❌ '+j.error}catch(e){$('yaml-preview').textContent='❌ '+e.message}}

async function yamlGenerateAndSend(){
  let data;try{data=await parseYamlViaAPI($('yaml-editor').value)}catch(e){toast('YAML错误');return}
  try{const r1=await fetch('/api/epd_display/generate',{method:'POST',headers:authH(),body:JSON.stringify(data)});const j1=await r1.json();if(!r1.ok){toast('❌ '+j1.error);return}
    const r2=await fetch('/api/services/epd_display/display_image',{method:'POST',headers:authH(),body:JSON.stringify({image_path:j1.path,canvas:haConfig.defaults.canvas,dither_mode:haConfig.defaults.dither_mode})});if(r2.ok)toast('✅ 已生成并发送');else toast('❌ 发送失败')}catch(e){toast('❌ '+e.message)}}

function yamlTestTemplate(){$('tpl-test-input').value='';$('tpl-test-result').textContent='结果';$('tpl-test-modal').classList.add('open')}
async function runTemplateTest(){const tpl=$('tpl-test-input').value;try{const r=await fetch('/api/epd_display/template_preview',{method:'POST',headers:authH(),body:JSON.stringify({template:tpl})});const j=await r.json();$('tpl-test-result').textContent=r.ok?'✅ '+j.result:'❌ '+j.error}catch(e){$('tpl-test-result').textContent='❌ '+e.message}}

// ── Keyboard ──
document.addEventListener('keydown',e=>{if(e.target.tagName==='INPUT'||e.target.tagName==='TEXTAREA')return;if(e.key==='Delete'||e.key==='Backspace'){delSelected();e.preventDefault()}if(e.key==='v')setTool('select');if(e.key==='r')setTool('rectangle');if(e.key==='l')setTool('line');if(e.key==='p')setTool('point');if(e.key==='t')setTool('text');if(e.key==='Escape'){selIdx=-1;refreshList();redraw();hideProps()}});

// ══════ HA Background Image Picker ══════
let bgPickerFiles = [], bgPickerSel = null, bgPickerDir = '';

async function openBgPicker() {
  bgPickerSel = null;
  bgPickerDir = '';
  $('bg-search').value = '';
  $('bg-confirm-btn').disabled = true;
  $('bg-picker-modal').classList.add('open');
  await loadBgList();
}

async function loadBgList(subdir) {
  if (subdir !== undefined) bgPickerDir = subdir;
  const search = $('bg-search').value.trim();
  const params = new URLSearchParams();
  if (bgPickerDir) params.set('subdir', bgPickerDir);
  if (search)      params.set('search', search);
  $('bg-picker-grid').innerHTML = '<div style="color:var(--text3);font-size:12px;padding:20px 0">加载中…</div>';
  $('bg-dir-row').innerHTML = '';
  try {
    const r = await fetch('/api/epd_display/media_list?' + params, { headers: authH() });
    const j = await r.json();
    if (!r.ok) { $('bg-picker-grid').innerHTML = `<div style="color:var(--warn)">${j.error||'错误'}</div>`; return; }
    bgPickerFiles = j.files || [];
    renderBgBreadcrumb();
    renderBgDirs(j.dirs || []);
    renderBgGrid(bgPickerFiles);
  } catch(e) {
    $('bg-picker-grid').innerHTML = `<div style="color:var(--warn)">请求失败: ${e.message}</div>`;
  }
}

function renderBgBreadcrumb() {
  const parts = bgPickerDir ? bgPickerDir.split('/') : [];
  let html = '<a data-action="loadBgList" data-arg="" style="cursor:pointer">根目录</a>';
  let built = '';
  parts.forEach((p, i) => {
    built += (built ? '/' : '') + p;
    const path = built;
    html += ` / <a data-action="loadBgList" data-arg="${path}" style="cursor:pointer">${p}</a>`;
  });
  $('bg-breadcrumb').innerHTML = html;
}

function renderBgDirs(dirs) {
  const c = $('bg-dir-row');
  c.innerHTML = '';
  dirs.forEach(d => {
    const btn = document.createElement('button');
    btn.className = 'btn btn-s btn-sm';
    btn.textContent = '📁 ' + d.name;
    btn.onclick = () => loadBgList(d.path.replace(/^www\/?/, ''));
    c.appendChild(btn);
  });
}

function renderBgGrid(files) {
  const grid = $('bg-picker-grid');
  grid.innerHTML = '';
  if (!files.length) {
    grid.innerHTML = '<div style="color:var(--text3);font-size:12px;padding:20px 0">此目录下没有图片</div>';
    return;
  }
  files.forEach(f => {
    const div = document.createElement('div');
    div.className = 'bg-thumb' + (bgPickerSel === f.abs_path ? ' sel' : '');
    div.dataset.abs = f.abs_path;
    div.dataset.preview = f.preview_url;
    div.innerHTML = `
      <img src="${f.preview_url}" loading="lazy" onerror="this.style.display='none'">
      <div class="label" title="${f.name}">${f.name}</div>`;
    div.onclick = () => {
      bgPickerSel = f.abs_path;
      bgPickerSelPreview = f.preview_url;
      document.querySelectorAll('.bg-thumb').forEach(t => t.classList.remove('sel'));
      div.classList.add('sel');
      $('bg-confirm-btn').disabled = false;
    };
    grid.appendChild(div);
  });
}

function bgSearch() {
  // debounce slightly
  clearTimeout(window._bgSearchTimer);
  window._bgSearchTimer = setTimeout(() => loadBgList(), 300);
}

let bgPickerSelPreview = '';

function confirmBgPick() {
  if (!bgPickerSel) return;
  // Load via proxy URL as an Image object, set as bgImg for canvas preview
  const img = new Image();
  img.crossOrigin = 'anonymous';
  img.onload = () => {
    bgImg = img;
    bgImgPath = bgPickerSel;   // absolute FS path – passed to backend as background_image
    // show path hint
    const row = $('bg-path-row');
    if (row) { row.textContent = bgPickerSel; row.style.display = 'block'; }
    redraw();
    toast('✅ 已设置底图');
  };
  img.onerror = () => toast('❌ 图片加载失败');
  img.src = bgPickerSelPreview;
  closeModal('bg-picker-modal');
}

// ══════ Image element helpers ══════

// 将服务器绝对路径 /config/www/... 转换为 HA /local/... 代理 URL 用于预览
function imgPathToPreviewUrl(path){
  if(!path)return null;
  // /config/www/xxx → /local/xxx
  const m=path.match(/^\/config\/www\/(.+)$/);
  if(m)return'/local/'+m[1];
  // /config/epd_images/xxx → /local/epd_images/xxx (symlink needed) 或 直接用 media_list abs url
  return null;
}

// 通用：给 element 加载 _img_obj（Image 对象）
function _loadImgObj(el){
  const url=imgPathToPreviewUrl(el.path);
  if(!url)return;
  const im=new Image();im.crossOrigin='anonymous';
  im.onload=()=>{el._img_obj=im;refreshList();redraw();};
  im.onerror=()=>{el._img_obj=null;};
  im.src=url;
}

// 从 JSON 导入后恢复所有 image 元素的预览对象
function restoreImgObjs(){
  elements.forEach(el=>{if(el.type==='image'&&el.path&&!el._img_obj)_loadImgObj(el);});
}

// 工具栏"从HA选择"按钮：选择后设置 img-path + 显示缩略图
let _imgPickerTarget=null; // 'tool' | 'prop'
// ── 图标工具本地文件上传 ──
let _imgToolSvgContent = '';  // 当前工具选中的 SVG 内容（字符串）
let _imgToolDataUrl = '';     // 位图 data URL（用于画布预览）

$('img-local-file').addEventListener('change', function(e) {
  const f = e.target.files[0];
  if (!f) return;
  const isSvg = f.name.toLowerCase().endsWith('.svg') || f.type === 'image/svg+xml';
  const reader = new FileReader();
  if (isSvg) {
    reader.onload = ev => {
      _imgToolSvgContent = ev.target.result;
      _imgToolDataUrl = '';
      // 用 Blob URL 预览
      const blob = new Blob([_imgToolSvgContent], {type:'image/svg+xml'});
      const url = URL.createObjectURL(blob);
      const prev = $('img-tool-preview'), thumb = $('img-tool-thumb');
      prev.src = url; thumb.style.display = 'block';
      $('img-path').value = '';  // 清空路径，以 svg_content 优先
      toast('📄 SVG已读取: ' + f.name);
    };
    reader.readAsText(f);
  } else {
    reader.onload = ev => {
      _imgToolDataUrl = ev.target.result;
      _imgToolSvgContent = '';
      const prev = $('img-tool-preview'), thumb = $('img-tool-thumb');
      prev.src = _imgToolDataUrl; thumb.style.display = 'block';
      toast('🖼 图片已加载: ' + f.name + '（需服务器路径才能渲染）');
    };
    reader.readAsDataURL(f);
  }
  e.target.value = '';
});
function openImgPickerForProp(){_imgPickerTarget='prop';_openImgPicker();}

// 属性面板：本地文件读取到 svg_content
function propLoadLocalImg(input){
  if(selIdx<0||!input.files[0])return;
  const el=elements[selIdx]; const f=input.files[0];
  const isSvg=f.name.toLowerCase().endsWith('.svg')||f.type==='image/svg+xml';
  const reader=new FileReader();
  if(isSvg){
    reader.onload=ev=>{
      el.svg_content=ev.target.result; el.path=''; el._img_obj=null;
      const blob=new Blob([el.svg_content],{type:'image/svg+xml'});
      const url=URL.createObjectURL(blob);
      const im=new Image();im.crossOrigin='anonymous';
      im.onload=()=>{el._img_obj=im;showProps(selIdx);redraw()};im.src=url;
      toast('SVG已嵌入: '+f.name);
    };
    reader.readAsText(f);
  } else {
    reader.onload=ev=>{
      el.svg_content=''; el._img_obj=null;
      const im=new Image();im.onload=()=>{el._img_obj=im;showProps(selIdx);redraw()};
      im.src=ev.target.result;
      toast('图片已加载（需服务器路径渲染）');
    };
    reader.readAsDataURL(f);
  }
  input.value='';
}
function clearPropSvgContent(){
  if(selIdx<0)return;
  elements[selIdx].svg_content='';elements[selIdx]._img_obj=null;
  showProps(selIdx);redraw();
}

function _openImgPicker(){
  // 复用 bg-picker-modal，但覆盖确认回调
  bgPickerSel=null;bgPickerSelPreview='';
  $('bg-search').value='';
  $('bg-confirm-btn').disabled=true;
  $('bg-confirm-btn').textContent='✅ 插入图标';
  $('bg-picker-modal').querySelector('h2').textContent='📂 选择图标文件';
  $('bg-picker-modal').classList.add('open');
  // 重写确认按钮行为
  $('bg-confirm-btn').onclick=_confirmImgPick;
  loadBgList();
}

function _confirmImgPick(){
  if(!bgPickerSel)return;
  if(_imgPickerTarget==='tool'){
    $('img-path').value=bgPickerSel;
    // 预览缩略图
    const thumb=$('img-tool-thumb'),prev=$('img-tool-preview');
    if(bgPickerSelPreview){prev.src=bgPickerSelPreview;thumb.style.display='block';}
  }else if(_imgPickerTarget==='prop'&&selIdx>=0){
    const el=elements[selIdx];
    el.path=bgPickerSel;el._img_obj=null;
    _loadImgObj(el);
    // 更新属性面板路径输入框
    const pp=$('p-imgpath');if(pp)pp.value=bgPickerSel;
    showProps(selIdx);
  }
  // 恢复bg-picker原来的标题和回调
  $('bg-confirm-btn').textContent='✅ 使用选中图片';
  $('bg-picker-modal').querySelector('h2').textContent='📂 从 HA 选择底图';
  $('bg-confirm-btn').onclick=confirmBgPick;
  closeModal('bg-picker-modal');
  toast('✅ 已选择: '+bgPickerSel.split('/').pop());
}

// 属性面板"重载预览"
function reloadImgPreview(){
  if(selIdx<0)return;
  const el=elements[selIdx];
  const pp=$('p-imgpath');if(pp&&pp.value)el.path=pp.value;
  el._img_obj=null;
  _loadImgObj(el);
  toast('重新加载中…');
}
function pickCalendarEntity(){
  entityPickCb=(eid)=>{
    const inp=$('cal-entities');
    if(inp){const cur=inp.value.trim();inp.value=cur?(cur+', '+eid):eid;}
  };
  openEntityPicker();
}
function pickCalEntityForProp(){
  entityPickCb=(eid)=>{
    const inp=$('p-cal-ents');
    if(inp){const cur=inp.value.trim();inp.value=cur?(cur+', '+eid):eid;}
    if(selIdx>=0){const el=elements[selIdx];if(el&&el.type==='calendar'){const cur=(el.calendar_entities||[]);if(!cur.includes(eid))el.calendar_entities=[...cur,eid];}}
  };
  openEntityPicker();
}
async function fetchCalPreviewForProp(){
  if(selIdx<0)return;
  const el=elements[selIdx];
  if(!el||el.type!=='calendar')return;
  const ents=el.calendar_entities||[];
  if(!ents.length){toast('请先设置日历实体');return}
  const now=new Date();
  const yr=el.year||now.getFullYear();
  const mo=el.month||now.getMonth()+1;
  const params=ents.map(e=>`entity_id=${encodeURIComponent(e)}`).join('&');
  try{
    const r=await fetch(`/api/epd_display/calendar_events?${params}&year=${yr}&month=${mo}`,{headers:authH()});
    if(r.ok){const j=await r.json();el._preview_events=j.events||[];redraw();showProps(selIdx);toast(`已加载 ${el._preview_events.length} 条事件`);}
    else{const j=await r.json();toast('❌ '+j.error);}
  }catch(e){toast('❌ '+e.message);}
}

function _drawCalendarPreview(ctx, el){
  const x=el.x, y=el.y, w=el.width||380, h=el.height||280;
  const now=new Date();
  const yr=el.year||now.getFullYear();
  const mo=(el.month||now.getMonth()+1)-1;
  const lang=el.lang||'zh';
  const fwd=el.first_weekday||0;
  const events=el._preview_events||[];
  ctx.save();
  ctx.fillStyle='#FFFFFF';ctx.strokeStyle='#CCCCCC';ctx.lineWidth=1;
  ctx.fillRect(x,y,w,h);ctx.strokeRect(x,y,w,h);
  const headerH=Math.round(h*0.12);
  ctx.fillStyle='#1A4B8C';ctx.fillRect(x,y,w,headerH);
  ctx.fillStyle='#FFFFFF';ctx.font=`bold ${Math.round(headerH*0.55)}px sans-serif`;
  ctx.textBaseline='middle';ctx.textAlign='center';
  const mZh=['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月'];
  const mEn=['January','February','March','April','May','June','July','August','September','October','November','December'];
  const title=lang==='zh'?`${yr}年 ${mZh[mo]}`:`${mEn[mo]} ${yr}`;
  ctx.fillText(title,x+w/2,y+headerH/2);
  const wdH=Math.round(h*0.09),wdY=y+headerH,cellW=w/7;
  const dZh=fwd===0?['一','二','三','四','五','六','日']:['日','一','二','三','四','五','六'];
  const dEn=fwd===0?['Mo','Tu','We','Th','Fr','Sa','Su']:['Su','Mo','Tu','We','Th','Fr','Sa'];
  const days=lang==='zh'?dZh:dEn;
  ctx.font=`${Math.round(wdH*0.55)}px sans-serif`;
  days.forEach((d,i)=>{
    const isW=(fwd===0&&i>=5)||(fwd===6&&i===0);
    ctx.fillStyle='#F0F4F8';ctx.fillRect(x+i*cellW,wdY,cellW,wdH);
    ctx.fillStyle=isW?'#CC3333':'#333333';ctx.fillText(d,x+i*cellW+cellW/2,wdY+wdH/2);
  });
  const gridY=wdY+wdH,gridH=h-(headerH+wdH);
  const firstDay=new Date(yr,mo,1).getDay();
  const offset=fwd===0?(firstDay+6)%7:firstDay;
  const dim=new Date(yr,mo+1,0).getDate();
  const rows=Math.ceil((offset+dim)/7);
  const cellH=gridH/rows;
  const todayD=new Date(),isThisMo=todayD.getFullYear()===yr&&todayD.getMonth()===mo;
  const evDays=new Set();
  events.forEach(ev=>{const d=new Date(ev.start);if(d.getFullYear()===yr&&d.getMonth()===mo)evDays.add(d.getDate());});
  ctx.font=`${Math.round(Math.min(cellH,cellW)*0.38)}px sans-serif`;
  ctx.textAlign='center';ctx.textBaseline='middle';
  for(let i=0;i<rows*7;i++){
    const col=i%7,row=Math.floor(i/7),day=i-offset+1,inM=day>=1&&day<=dim;
    const cx=x+col*cellW,cy=gridY+row*cellH;
    ctx.fillStyle=(row%2===0)?'#FFFFFF':'#F8FBFF';ctx.fillRect(cx,cy,cellW,cellH);
    ctx.strokeStyle='#E0E8F0';ctx.lineWidth=0.5;ctx.strokeRect(cx,cy,cellW,cellH);
    if(!inM)continue;
    const isToday=isThisMo&&day===todayD.getDate();
    if(isToday){
      const r=Math.min(cellW,cellH)*0.38;
      ctx.fillStyle='#1A4B8C';ctx.beginPath();ctx.arc(cx+cellW/2,cy+cellH*0.42,r,0,Math.PI*2);ctx.fill();
      ctx.fillStyle='#FFFFFF';
    } else {ctx.fillStyle=((fwd===0&&col>=5)||(fwd===6&&col===0))?'#CC3333':'#222222';}
    ctx.fillText(String(day),cx+cellW/2,cy+cellH*0.42);
    if(evDays.has(day)){ctx.fillStyle='#E06020';ctx.beginPath();ctx.arc(cx+cellW/2,cy+cellH*0.78,Math.min(cellW,cellH)*0.08,0,Math.PI*2);ctx.fill();}
  }
  ctx.restore();
}

// ── Init
redraw();refreshList();

// ── entity-search input listener (was oninput=)
$('entity-search').addEventListener('input', () => filterEntities());
$('bg-search').addEventListener('input', () => bgSearch());

// ── p-svg-local change listener (was onchange=)
document.addEventListener('change', e => {
  if (e.target && e.target.id === 'p-svg-local') propLoadLocalImg(e.target);
});

// ── 统一事件委托：处理所有 data-action 按钮/链接
// 解决 HA panel iframe CSP 不允许 inline onclick 的问题
const _actionMap = {
  showPage:               n => showPage(n),
  closeModal:             id => closeModal(id),
  copyYaml:               () => { navigator.clipboard.writeText($('yaml-out').value); toast('已复制'); },
  // 发送页
  sendUpload:             () => sendUpload(),
  sendUrl:                () => sendUrl(),
  // 画布/工具
  applyCanvas:            () => applyCanvas(),
  clearBg:                () => clearBg(),
  bgFileClick:            () => $('bg-file').click(),
  openBgPicker:           () => openBgPicker(),
  setTool:                t  => setTool(t),
  // 图层/元素
  addEntityText:          () => addEntityText(),
  delElem:                i  => delElem(parseInt(i)),
  delSelected:            () => delSelected(),
  clearAll:               () => clearAll(),
  // 属性面板
  applyProps:             () => applyProps(),
  pickEntityForProp:      () => pickEntityForProp(),
  refreshEntityState:     () => refreshEntityState(),
  previewComputed:        () => previewComputed(),
  pickEntityForTbProp:    () => pickEntityForTbProp(),
  refreshTbEntityState:   () => refreshTbEntityState(),
  previewTbComputed:      () => previewTbComputed(),
  switchTbType:           t  => switchTbType(t),
  setTbMode:              m  => setTbMode(m),
  pickEntityForTb:        () => pickEntityForTb(),
  clearPropSvgContent:    () => clearPropSvgContent(),
  fetchCalPreviewForProp: () => fetchCalPreviewForProp(),
  pickCalEntityForProp:   () => pickCalEntityForProp(),
  openImgPickerForProp:   () => openImgPickerForProp(),
  pSvgLocalClick:         () => $('p-svg-local') && $('p-svg-local').click(),
  reloadImgPreview:       () => reloadImgPreview(),
  imgLocalFileClick:      () => $('img-local-file').click(),
  openImgPickerForTool:   () => openImgPickerForTool(),
  // 实体/背景选择器
  openEntityPicker:       () => openEntityPicker(),
  loadBgList:             arg => loadBgList(arg||''),
  confirmBgPick:          () => confirmBgPick(),
  // 日历
  pickCalendarEntity:     () => pickCalendarEntity(),
  // 导入/导出
  openYaml:               () => openYaml(),
  exportJSON:             () => exportJSON(),
  importJSON:             () => importJSON(),
  downloadPNG:            () => downloadPNG(),
  generateOnHA:           () => generateOnHA(),
  generateAndSend:        () => generateAndSend(),
  // 模板管理
  loadTemplateList:       () => loadTemplateList(),
  saveCurrentAsTemplate:  () => saveCurrentAsTemplate(),
  deleteTpl:              n  => deleteTpl(n),
  yamlSaveAsTemplate:     () => yamlSaveAsTemplate(),
  confirmSaveTemplate:    () => confirmSaveTemplate(),
  yamlPreviewGenerate:    () => yamlPreviewGenerate(),
  yamlGenerateAndSend:    () => yamlGenerateAndSend(),
  yamlTestTemplate:       () => yamlTestTemplate(),
  runTemplateTest:        () => runTemplateTest(),
};

document.addEventListener('click', e => {
  const btn = e.target.closest('[data-action]');
  if (!btn) return;
  const action = btn.dataset.action;
  const arg    = btn.dataset.arg;
  console.log('[EPD] click action=', action, 'arg=', arg);
  const fn = _actionMap[action];
  if (fn) fn(arg);
  else console.warn('[EPD] unknown action:', action);
});
