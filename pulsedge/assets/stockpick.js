// PulsePick: add holdings by searching. Type part of a company name, its NSE symbol or its ISIN; the list shows the
// matching Nifty 500 companies (symbol, full name, sector, ISIN when known). Pick one, set the quantity if you like,
// pick the next, then add them all. Pasting several lines ("Sun Pharma 35", "TCS 40") stages every line it recognises.
// Used by the terminal (My stocks), the landing page, the news calendar and the monthly report. It only builds the
// form: the page decides where the holdings are saved (the browser's pe_hold list).
//
//   var p = PulsePick.create({onAdd: function(items){ ... items = [{s:"SUNPHARMA", q:35}, ...] },
//                             held: function(sym){ return true if already in the list },   // optional
//                             list: function(){ return the universe if the page has it },  // optional
//                             button: "Add to My stocks"});                                 // optional
//   container.appendChild(p.el);
window.PulsePick = (function(){
  "use strict";
  var uniP=null,css=false,n=0;
  function universe(){
    if(!uniP)uniP=fetch("data/universe.json",{cache:"no-store"}).then(function(r){return r.ok?r.json():{}}).then(function(j){return j.stocks||[]}).catch(function(){return []});
    return uniP;
  }
  function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e}
  function norm(s){return String(s||"").toLowerCase().replace(/&/g," and ").replace(/\b(ltd|limited|the|india)\b\.?/g," ").replace(/[^a-z0-9]+/g," ").trim()}
  function short(n){return String(n||"").replace(/\s+(Limited|Ltd\.?)$/i,"")}

  // best matches for what was typed: symbol and ISIN first, then names that start with or contain the words
  function search(list,text,max){
    var raw=String(text||"").trim(),q=norm(raw),up=raw.toUpperCase().replace(/\.(NS|BO)$|-(EQ|BE)$/,""),out=[];
    if(!q)return out;
    var words=q.split(" ");
    list.forEach(function(st){
      var sym=st.symbol,nm=" "+norm(st.name)+" ",sc=0;
      if(sym===up||(st.isin&&st.isin===up))sc=100;
      else if(sym.indexOf(up)===0)sc=86-Math.min(6,sym.length-up.length);
      else if(nm.indexOf(" "+q)===0)sc=80;
      else if(nm.indexOf(" "+q)>0)sc=70;
      else if(words.every(function(w){return nm.indexOf(" "+w)>=0}))sc=62;
      else if(q.length>=3&&(nm.indexOf(q)>=0||sym.toLowerCase().indexOf(q.replace(/ /g,""))>=0))sc=45;
      if(sc)out.push({sc:sc,st:st});
    });
    return out.sort(function(a,b){return b.sc-a.sc||(a.st.symbol<b.st.symbol?-1:1)}).slice(0,max||8);
  }
  // one pasted line: "Sun Pharma 35", "TCS x 40", "INE002A01018, 10"
  function fromLine(list,line){
    var toks=line.trim().split(/[\s,;:]+/).filter(function(t){return t&&!/^(x|×|qty|shares|nos|@|-)$/i.test(t)}),q=null;
    if(toks.length>1&&/^[\d,]+(\.\d+)?$/.test(toks[toks.length-1]))q=Math.round(parseFloat(toks.pop().replace(/,/g,"")))||null;
    var hs=search(list,toks.join(" "),2);
    if(hs.length&&hs[0].sc>=62&&(hs.length===1||hs[0].sc>hs[1].sc||hs[0].sc===100))return {st:hs[0].st,q:q};
    return null;
  }

  function style(){
    if(css)return;css=true;
    var s=el("style");s.textContent=
    ".spk{--pp-bg:var(--panel,var(--card,#fff));--pp-fg:var(--fg,var(--ink,#16151a));--pp-mute:var(--mute,#6b6875);--pp-line:var(--line,#e4e2ea);"+
      "--pp-acc:var(--pur,var(--acc,#7c4dff));--pp-soft:var(--pur-soft,color-mix(in srgb,var(--pp-acc) 14%,transparent));--pp-fld:var(--fld,var(--panel2,var(--bg,transparent)));"+
      "--pp-mono:var(--mono,ui-monospace,'SF Mono',Menlo,Consolas,monospace);display:grid;gap:10px;color:var(--pp-fg)}"+
    ".spk-s{position:relative}"+
    ".spk-s input{width:100%;box-sizing:border-box;font-family:inherit;font-size:16px;line-height:1.4;color:var(--pp-fg);background:var(--pp-fld);border:1px solid var(--pp-line);border-radius:10px;padding:11px 12px 11px 36px}"+
    ".spk-s input:focus{outline:none;border-color:var(--pp-acc);box-shadow:0 0 0 3px color-mix(in srgb,var(--pp-acc) 18%,transparent)}"+
    ".spk-s svg{position:absolute;left:11px;top:50%;width:17px;height:17px;transform:translateY(-50%);fill:none;stroke:var(--pp-mute);stroke-width:2;stroke-linecap:round;pointer-events:none}"+
    ".spk-l{position:absolute;z-index:30;left:0;right:0;top:calc(100% + 6px);margin:0;padding:6px;list-style:none;background:var(--pp-bg);border:1px solid var(--pp-line);border-radius:10px;"+
      "box-shadow:0 18px 40px -16px rgba(0,0,0,.5);max-height:min(55vh,360px);overflow:auto}"+
    ".spk-l li{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:2px 10px;align-items:baseline;padding:8px 10px;border-radius:8px;cursor:pointer}"+
    ".spk-l li[aria-selected=true]{background:var(--pp-soft)}"+
    ".spk-l .k{font:600 12.5px/1.4 var(--pp-mono);color:var(--pp-acc);min-width:6.5em}"+
    ".spk-l .n{font-size:14.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}"+
    ".spk-l .t{font-size:12px;color:var(--pp-mute);white-space:nowrap}"+
    ".spk-l .d{grid-column:2/-1;font-size:12px;color:var(--pp-mute);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}"+
    ".spk-l .none{display:block;cursor:default;color:var(--pp-mute);font-size:13.5px}"+
    ".spk-st{list-style:none;margin:0;padding:0;display:grid;gap:6px}"+
    ".spk-st li{display:grid;grid-template-columns:minmax(0,1fr) 108px auto;gap:2px 8px;align-items:center;border:1px solid var(--pp-line);border-radius:10px;padding:7px 8px 7px 12px;background:var(--pp-bg)}"+
    ".spk-st b{font:600 13px/1.3 var(--pp-mono)}"+
    ".spk-st .n{grid-column:1;font-size:13px;color:var(--pp-mute);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}"+
    ".spk-st input{grid-column:2;grid-row:1/3;width:100%;box-sizing:border-box;font:15px/1.3 var(--pp-mono);color:var(--pp-fg);background:var(--pp-fld);border:1px solid var(--pp-line);border-radius:8px;padding:7px 8px}"+
    ".spk-st input:focus{outline:none;border-color:var(--pp-acc)}"+
    ".spk-st button{grid-column:3;grid-row:1/3;background:none;border:1px solid var(--pp-line);border-radius:8px;color:var(--pp-mute);padding:6px 9px;font-size:13px;cursor:pointer}"+
    ".spk-r{display:flex;flex-wrap:wrap;gap:8px;align-items:center}"+
    ".spk-go{font-family:inherit;font-weight:600;font-size:14px;line-height:1;border:1px solid var(--pp-acc);background:var(--pp-acc);color:#fff;border-radius:9px;padding:10px 14px;cursor:pointer}"+
    ".spk-go[disabled]{opacity:.45;cursor:default}"+
    ".spk-h{margin:0;font-size:12.5px;color:var(--pp-mute)}"+
    ".spk-m{margin:0;font-size:13px}.spk-m.err{color:var(--red-l,#c8323c)}"+
    "@media (max-width:520px){.spk-st li{grid-template-columns:minmax(0,1fr) 84px auto}.spk-l .t{display:none}}";
    document.head.appendChild(s);
  }

  function create(opts){
    opts=opts||{};style();
    var id="spk"+(++n),list=[],hits=[],sel=-1,staged=[];
    function getList(){var l=opts.list&&opts.list();return l&&l.length?l:list}
    universe().then(function(l){list=l;if(inp.value.trim())find()});

    var root=el("div","spk"),box=el("div","spk-s");
    box.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.6-3.6"/></svg>';
    var inp=el("input");inp.type="search";inp.autocomplete="off";inp.spellcheck=false;
    inp.placeholder=opts.placeholder||"Search a company, NSE symbol or ISIN";
    inp.setAttribute("role","combobox");inp.setAttribute("aria-autocomplete","list");inp.setAttribute("aria-expanded","false");
    inp.setAttribute("aria-controls",id+"-l");inp.setAttribute("aria-label",opts.label||"Search a stock to add");
    var ul=el("ul","spk-l");ul.id=id+"-l";ul.setAttribute("role","listbox");ul.hidden=true;
    box.append(inp,ul);
    var st=el("ul","spk-st"),row=el("div","spk-r"),go=el("button","spk-go");go.type="button";
    var msg=el("p","spk-m");msg.setAttribute("aria-live","polite");msg.hidden=true;
    var hint=el("p","spk-h",opts.hint||"Type a few letters of the name, the NSE symbol or the ISIN, and pick the right company from the list. You can also paste several lines, like \"Sun Pharma 35\".");
    row.append(go);root.append(box,st,row,msg,hint);

    function say(t,err){msg.textContent=t||"";msg.className="spk-m"+(err?" err":"");msg.hidden=!t}
    function isHeld(s){return !!(opts.held&&opts.held(s))}
    function find(){hits=search(getList(),inp.value,8);sel=hits.length?0:-1;show()}
    function show(){
      ul.textContent="";
      var t=inp.value.trim();
      if(!t){ul.hidden=true;inp.setAttribute("aria-expanded","false");return}
      if(!hits.length){var li=el("li","none",getList().length?"No Nifty 500 company matches \""+t+"\". Try part of the name or the NSE symbol.":"Loading the stock list…");ul.appendChild(li)}
      hits.forEach(function(h,i){
        var li=el("li");li.id=id+"-o"+i;li.setAttribute("role","option");li.setAttribute("aria-selected",i===sel?"true":"false");
        var already=isHeld(h.st.symbol)?"In your list":staged.some(function(x){return x.st.symbol===h.st.symbol})?"Picked":"";
        li.append(el("span","k",h.st.symbol),el("span","n",short(h.st.name)),el("span","t",already),
          el("span","d",[h.st.sector,h.st.isin].filter(Boolean).join(" · ")));
        li.addEventListener("mousedown",function(e){e.preventDefault();pick(i)});
        ul.appendChild(li);
      });
      ul.hidden=false;inp.setAttribute("aria-expanded","true");
      if(sel>=0)inp.setAttribute("aria-activedescendant",id+"-o"+sel);else inp.removeAttribute("aria-activedescendant");
    }
    function stage(stk,q,focusQty){
      var ex=staged.filter(function(x){return x.st.symbol===stk.symbol})[0];
      if(ex){if(q)ex.q=q}else staged.push(ex={st:stk,q:q||null});
      draw();
      if(focusQty){var f=st.querySelector('input[data-s="'+stk.symbol+'"]');if(f)f.focus()}
    }
    function pick(i){
      var h=hits[i];if(!h)return;
      inp.value="";hits=[];show();say("");
      stage(h.st,null,true);
    }
    function draw(){
      st.textContent="";
      staged.forEach(function(x){
        var li=el("li"),q=el("input"),rm=el("button",null,"✕");
        q.type="number";q.min="0";q.step="1";q.inputMode="numeric";q.placeholder="Qty";q.value=x.q||"";q.dataset.s=x.st.symbol;
        q.setAttribute("aria-label","Quantity of "+x.st.symbol+" (optional)");
        q.addEventListener("input",function(){var v=parseInt(q.value,10);x.q=v>0?v:null});
        q.addEventListener("keydown",function(e){if(e.key==="Enter"){e.preventDefault();inp.focus()}});
        rm.type="button";rm.setAttribute("aria-label","Remove "+x.st.symbol);
        rm.addEventListener("click",function(){staged=staged.filter(function(y){return y!==x});draw();inp.focus()});
        li.append(el("b",null,x.st.symbol+(isHeld(x.st.symbol)?"  · in your list":"")),q,rm,el("span","n",short(x.st.name)+(x.st.isin?" · "+x.st.isin:"")));
        st.appendChild(li);
      });
      go.disabled=!staged.length;
      go.textContent=staged.length>1?(opts.buttonMany||"Add these "+staged.length+" stocks"):(opts.button||"Add to my stocks");
    }
    go.addEventListener("click",function(){
      if(!staged.length){inp.focus();return}
      var items=staged.map(function(x){return {s:x.st.symbol,q:x.q||null}});
      staged=[];draw();say("");
      if(opts.onAdd)opts.onAdd(items);
    });
    inp.addEventListener("input",function(){find()});
    inp.addEventListener("focus",function(){if(inp.value.trim())find()});
    inp.addEventListener("blur",function(){setTimeout(function(){ul.hidden=true;inp.setAttribute("aria-expanded","false")},150)});
    inp.addEventListener("keydown",function(e){
      if(e.key==="ArrowDown"||e.key==="ArrowUp"){
        if(!hits.length)return;e.preventDefault();sel=(sel+(e.key==="ArrowDown"?1:hits.length-1))%hits.length;
        Array.prototype.forEach.call(ul.children,function(li,i){li.setAttribute("aria-selected",i===sel?"true":"false")});
        inp.setAttribute("aria-activedescendant",id+"-o"+sel);if(ul.children[sel])ul.children[sel].scrollIntoView({block:"nearest"});
      }else if(e.key==="Enter"){
        e.preventDefault();
        if(sel>=0&&hits[sel])pick(sel);
        else if(!inp.value.trim()&&staged.length)go.click();
      }else if(e.key==="Escape"){hits=[];show()}
    });
    // several lines pasted at once: stage every line that names one company clearly, list the rest
    inp.addEventListener("paste",function(e){
      var t=(e.clipboardData||window.clipboardData);t=t&&t.getData("text");
      if(!t||!/[\n;]/.test(t.trim()))return;
      e.preventDefault();
      var bad=[],good=0;
      t.split(/[\r\n;]+/).forEach(function(line){if(!line.trim())return;var r=fromLine(getList(),line);if(r){stage(r.st,r.q,false);good++}else bad.push(line.trim().slice(0,30))});
      say((good?"Picked "+good+". ":"")+(bad.length?"Couldn't match: "+bad.slice(0,5).join(", ")+(bad.length>5?" and "+(bad.length-5)+" more":"")+". Search for those one at a time.":"Check the quantities, then add."),!!bad.length);
    });
    draw();
    return {el:root,input:inp,focus:function(){inp.focus()},redraw:draw,staged:function(){return staged.length}};
  }
  return {create:create,search:search,universe:universe};
})();
