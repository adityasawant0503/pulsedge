/* PulsEdge hero scene: the triage, in 3D.
 *
 * Unread headlines drift in from far away and converge on the PulsEdge gate. At the gate each one gets its
 * verdict: most are set aside and fall away as ghosts; the few marked Watch or Act flip into terminal rows
 * and drop into the terminal preview below. It is the product's mechanism, drawn.
 *
 * Plain WebGL2, no libraries and no downloads: one instanced draw call of quads, shaded in the fragment
 * shader. Colours come from the page's CSS tokens and follow the theme. The scene pauses when it is off
 * screen or the tab is hidden, steps its quality down on slow devices, and draws a single still frame when
 * the viewer prefers reduced motion. Without WebGL2 the canvas is removed and the page looks as before.
 *
 * World units are CSS pixels on the z = 0 plane, x right, y down, z towards the viewer; the camera sits
 * CAM_D pixels in front of the canvas, so anchors can be taken straight from the page layout.
 */
(function(){
"use strict";
var cv=document.getElementById("h3d");
if(!cv)return;
var hero=cv.parentNode,stage=document.getElementById("stage"),h1=hero.querySelector("h1"),wrap=hero.querySelector(".w"),root=document.documentElement;
var gl=null;
try{gl=cv.getContext("webgl2",{alpha:true,premultipliedAlpha:true,antialias:false,depth:false,stencil:false,powerPreference:"low-power"})}catch(e){}
if(!gl||!stage||!h1||!wrap){cv.remove();return}

var VS=[
"#version 300 es",
"precision highp float;",
"layout(location=0) in vec2 q;",       // quad corner, -1..1
"layout(location=1) in vec3 iPos;",    // centre
"layout(location=2) in vec3 iAx;",     // half-extent along the card's x
"layout(location=3) in vec3 iAy;",     // half-extent along the card's y
"layout(location=4) in vec4 iCol;",    // verdict colour, opacity
"layout(location=5) in vec4 iMisc;",   // kind, seed, reveal, light
"uniform vec2 uRes;uniform vec3 uCam;uniform vec2 uFog;",
"out vec2 vP;out vec2 vH;out vec4 vCol;out vec4 vMisc;out float vFace;out float vFog;out float vShade;",
"void main(){",
"  vec3 p=iPos+iAx*q.x+iAy*q.y;",
"  float w=max(.05,(uCam.z-p.z)/uCam.z);",
"  vec2 s=uCam.xy+(p.xy-uCam.xy)/w;",
"  vec2 ndc=vec2(s.x/uRes.x*2.-1.,1.-s.y/uRes.y*2.);",
"  gl_Position=vec4(ndc*w,0.,w);",      // w keeps the interpolation perspective-correct
"  vH=vec2(length(iAx),length(iAy));vP=q*vH;vCol=iCol;vMisc=iMisc;",
"  vec3 n=normalize(cross(iAx,iAy));vFace=n.z;",
"  vShade=clamp(dot(n*sign(n.z+1e-5),normalize(vec3(-.35,-.6,.72))),0.,1.);",
"  vFog=clamp((-iPos.z-uFog.x)/(uFog.y-uFog.x),0.,1.);",
"}"].join("\n");

var FS=[
"#version 300 es",
"precision highp float;",
"in vec2 vP;in vec2 vH;in vec4 vCol;in vec4 vMisc;in float vFace;in float vFog;in float vShade;",
"uniform sampler2D uLab;",
"uniform vec3 uBg,uPaper,uPaperLine,uPaperBar,uTerm,uTermLine,uTermBar,uAcc;",
"uniform float uAdd,uTime;",
"out vec4 o;",
"float rbox(vec2 p,vec2 h,float r){vec2 d=abs(p)-h+r;return length(max(d,0.))+min(max(d.x,d.y),0.)-r;}",
"float fill(float d,float aa){return 1.-smoothstep(-aa,aa,d);}",
"float bar(float x0,float x1,float yc,float aa){",
"  vec2 h=vec2((x1-x0)*.5*vH.x,.16*vH.y);",
"  return fill(rbox(vP-vec2((x0+x1)*.5*vH.x,yc*vH.y),h,h.y),aa);}",
"void main(){",
"  float kind=vMisc.x;",
"  if(kind>4.5){",                      // soft glow
"    vec2 u=vP/vH;float l2=dot(u,u);",
"    float a=exp(-l2*3.2)*(1.-smoothstep(.7,1.,l2))*vCol.a;",
"    o=vec4(vCol.rgb*a,a*(1.-uAdd));return;",
"  }",
"  if(kind>3.5){",                      // the gate
"    float R=vH.x/2.4,l=length(vP),px=fwidth(l)+1e-4,d=abs(l-R);",
"    float core=1.-smoothstep(R*.016,R*.016+px*1.6,d);",
"    float halo=exp(-d/(R*.13))*.36;",
"    float lens=(1.-smoothstep(R-px,R+px,l))*.06;",
"    float f1=fract(uTime/2.8),f2=fract(uTime/2.8+.5);",
"    float p1=(1.-smoothstep(0.,R*.03+px*1.5,abs(l-R*(1.+.95*f1))))*(1.-f1)*(1.-f1)*.5;",
"    float p2=(1.-smoothstep(0.,R*.03+px*1.5,abs(l-R*(1.+.95*f2))))*(1.-f2)*(1.-f2)*.5;",
"    float hair=(1.-smoothstep(0.,px*1.4,abs(l-R*1.16)))*.22;",
"    vec3 c=mix(uAcc,vCol.rgb,vMisc.w);",
"    float a=clamp(core+halo+lens+p1+p2+hair,0.,1.)*vCol.a;",
"    o=vec4(mix(c,vec3(1.),core*.5*uAdd)*a,a*(1.-uAdd*(1.-core)*.9));return;",
"  }",
"  float d=rbox(vP,vH,min(vH.x,vH.y)*.36),aa=fwidth(d)*.9+1e-4;",
"  float body=fill(d,aa);if(body<.004)discard;",
"  float rev=vMisc.z,seed=vMisc.y,acc=step(1.5,kind),ign=(1.-acc)*step(.5,kind),act=step(2.5,kind);",
"  float front=step(0.,vFace),lw=max(1.3,aa*1.7);",
"  float edge=smoothstep(-lw-aa,-lw+aa,d);",
// an unread headline: paper with two lines of text
"  vec3 paper=uPaper*(.9+.12*vShade);",
"  float tu=max(bar(-.78,.12+.6*seed,-.3,aa),bar(-.78,-.25+.55*fract(seed*7.31),.3,aa));",
"  vec3 cu=mix(mix(paper,uPaperBar,front*tu),uPaperLine,edge);",
// a verdict: a terminal row with its chip
"  vec3 term=uTerm*(.86+.34*vShade);",
"  float ta=max(bar(-.12,.8,-.3,aa),bar(-.12,.2+.42*seed,.3,aa));",
"  vec3 ca=mix(term,uTermBar,front*ta*.85);",
"  vec2 ch=vec2(.31*vH.x,.42*vH.y),cp=vP-vec2(-.56*vH.x,0.);",
"  float dc=rbox(cp,ch,ch.y*.42),chip=fill(dc,aa)*front;",
"  vec2 uv=cp/ch;",
"  float lab=texture(uLab,vec2(.5+uv.x*(ch.x/ch.y)/8.,(1.5-act+uv.y*.5)/2.)).a;",
"  vec3 cc=mix(mix(term,vCol.rgb,smoothstep(-lw-aa,-lw+aa,dc)),vCol.rgb,act);",
"  cc=mix(cc,mix(vCol.rgb,uTerm,act),lab);",
"  ca=mix(ca,cc,chip);",
"  ca=mix(ca,mix(uTermLine,vCol.rgb,.62),edge);",
// set aside: a ghost outline
"  vec3 ci=mix(uBg,uPaperLine,.45+.55*edge);",
"  vec3 col=mix(cu,mix(ca,ci,ign),rev);",
"  float af=mix(1.,mix(1.,mix(.16,.95,edge),ign),rev);",
"  col=mix(col,uAcc,vMisc.w*.2*(1.-rev));",   // lit by the gate as it approaches
"  col=mix(col,uBg,vFog*.86);",
"  float a=body*vCol.a*af;",
"  o=vec4(col*a,a);",
"}"].join("\n");

var STRIDE=17,MAX=360,TAU=6.2831853;
var buf=new Float32Array(MAX*STRIDE),out=new Float32Array(MAX*STRIDE),zs=new Float32Array(MAX),ord=[];
var n=0,prog,vao,ibo,tex,U={};
var AX=[0,0,0],AY=[0,0,0];

function shader(type,src){
  var s=gl.createShader(type);gl.shaderSource(s,src);gl.compileShader(s);
  if(!gl.getShaderParameter(s,gl.COMPILE_STATUS)){var m=gl.getShaderInfoLog(s);gl.deleteShader(s);throw new Error(m)}
  return s;
}
function labels(){
  var c=document.createElement("canvas");c.width=256;c.height=128;
  var x=c.getContext("2d");
  x.fillStyle="#fff";x.textAlign="center";x.textBaseline="middle";
  x.font='600 36px "IBM Plex Mono",ui-monospace,"SF Mono",Menlo,Consolas,monospace';
  try{x.letterSpacing="4px"}catch(e){}
  x.fillText("ACT",130,33);x.fillText("WATCH",130,97);
  gl.bindTexture(gl.TEXTURE_2D,tex);
  gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,c);
  gl.generateMipmap(gl.TEXTURE_2D);
  gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR_MIPMAP_LINEAR);
  gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
}
function setup(){
  prog=gl.createProgram();
  gl.attachShader(prog,shader(gl.VERTEX_SHADER,VS));gl.attachShader(prog,shader(gl.FRAGMENT_SHADER,FS));
  gl.linkProgram(prog);
  if(!gl.getProgramParameter(prog,gl.LINK_STATUS))throw new Error(gl.getProgramInfoLog(prog));
  gl.useProgram(prog);
  ["uRes","uCam","uFog","uTime","uAdd","uBg","uPaper","uPaperLine","uPaperBar","uTerm","uTermLine","uTermBar","uAcc","uLab"].forEach(function(k){U[k]=gl.getUniformLocation(prog,k)});
  vao=gl.createVertexArray();gl.bindVertexArray(vao);
  var qb=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,qb);
  gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,1,1]),gl.STATIC_DRAW);
  gl.enableVertexAttribArray(0);gl.vertexAttribPointer(0,2,gl.FLOAT,false,0,0);
  ibo=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,ibo);gl.bufferData(gl.ARRAY_BUFFER,out.byteLength,gl.DYNAMIC_DRAW);
  var off=0;
  [3,3,3,4,4].forEach(function(size,i){
    gl.enableVertexAttribArray(i+1);gl.vertexAttribPointer(i+1,size,gl.FLOAT,false,STRIDE*4,off*4);gl.vertexAttribDivisor(i+1,1);off+=size;
  });
  tex=gl.createTexture();labels();gl.uniform1i(U.uLab,0);
  gl.disable(gl.DEPTH_TEST);gl.enable(gl.BLEND);gl.blendFunc(gl.ONE,gl.ONE_MINUS_SRC_ALPHA);gl.clearColor(0,0,0,0);
}

// ---------- colours from the page's tokens ----------
var ACT=[.24,.81,.56],WATCH=[.95,.7,.3],ACC=[.42,.26,.94];
function hex(v,fb){
  v=String(v||"").trim();
  var m=/^#([0-9a-f]{6})$/i.exec(v),s=m?m[1]:(/^#[0-9a-f]{3}$/i.test(v)?v.slice(1).replace(/./g,"$&$&"):fb),k=parseInt(s,16);
  return [(k>>16&255)/255,(k>>8&255)/255,(k&255)/255];
}
function mix(a,b,t){return [a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t,a[2]+(b[2]-a[2])*t]}
function theme(){
  var cs=getComputedStyle(root),g=function(k,fb){return hex(cs.getPropertyValue(k),fb)};
  var bg=g("--bg","fbfaff"),dark=bg[0]*.3+bg[1]*.59+bg[2]*.11<.4;
  var panel=g("--panel","ffffff"),line2=g("--line2","d8d4e3"),term=g("--term2","15141d"),fg=g("--termfg","ecebf3");
  ACC=g("--acc","6c43f0");ACT=g("--t-act","3ecf8e");WATCH=g("--t-watch","f2b24c");
  gl.useProgram(prog);
  gl.uniform1f(U.uAdd,dark?1:0);
  gl.uniform3fv(U.uBg,bg);
  gl.uniform3fv(U.uPaper,dark?mix(panel,fg,.07):panel);
  gl.uniform3fv(U.uPaperLine,dark?mix(line2,fg,.16):mix(line2,ACC,.2));
  gl.uniform3fv(U.uPaperBar,dark?mix(line2,fg,.07):mix(g("--line","e7e4ef"),ACC,.1));
  gl.uniform3fv(U.uTerm,dark?mix(term,fg,.05):term);
  gl.uniform3fv(U.uTermLine,g("--termline","272534"));
  gl.uniform3fv(U.uTermBar,mix(term,fg,.42));
  gl.uniform3fv(U.uAcc,ACC);
}

// ---------- layout: anchors come from the page ----------
var W=0,H=0,dpr=1,CAM_D=1200,cam=[0,0],G=[0,0,0],K=[0,0,0],C=[0,0,0],A=[0,0,1],B1=[1,0,0],B2=[0,1,0];
var wide=false,ringR=60,srcR=600,gateR=20,uSize=[62,20],aSize=[94,29],count=0,level=0;
var TOP=80;   // the canvas starts this far above the hero, so the stream carries on under the translucent header
var rnd=null;
function seedRandoms(){
  var s=0x9e3779b9,r=function(){s|=0;s=s+0x6d2b79f5|0;var t=Math.imul(s^s>>>15,1|s);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296};
  rnd=new Float32Array(200*8);for(var i=0;i<rnd.length;i++)rnd[i]=r();
}
function unproject(sx,sy,z){var k=(CAM_D-z)/CAM_D;return [cam[0]+(sx-cam[0])*k,cam[1]+(sy-cam[1])*k,z]}
function norm(v){var l=Math.hypot(v[0],v[1],v[2])||1;return [v[0]/l,v[1]/l,v[2]/l]}
function cross(a,b){return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]}
function layout(){
  var hr=hero.getBoundingClientRect(),tr=h1.getBoundingClientRect(),wr=wrap.getBoundingClientRect();
  var st=stage.offsetTop+TOP,top=hr.top-TOP,cap=level>0?1:(hr.width*st>1.1e6?1.5:2);
  W=Math.max(1,Math.round(hr.width));H=Math.max(1,Math.min(st+150,hero.clientHeight+TOP));
  dpr=Math.min(window.devicePixelRatio||1,cap);
  cv.style.height=H+"px";cv.width=Math.round(W*dpr);cv.height=Math.round(H*dpr);
  gl.viewport(0,0,cv.width,cv.height);
  var free=wr.right-tr.right;wide=W>=900&&free>300;
  cam=[W*.5,H*.42];
  var gs,fs,ks,gz,fz,kz,mask="none";
  if(wide){
    CAM_D=1250;ringR=112;srcR=900;gateR=44;uSize=[60,19.5];aSize=[100,31];count=150;
    gs=[(tr.right+wr.right)/2-hr.left+30,tr.top-top+tr.height*.56];gz=-430;
    fs=[Math.min(W-40,gs[0]+250),TOP-40];fz=-3400;
    ks=[gs[0]-60,st+46];kz=40;
    var m=(tr.right-hr.left)/W*100;
    mask="linear-gradient(90deg,transparent "+(m-16).toFixed(1)+"%,#000 "+(m+5).toFixed(1)+"%)";
  }else{
    var k=W<560?1:1.3;
    CAM_D=950;ringR=52*k;srcR=350*k;gateR=20*k;uSize=[40*k,13*k];aSize=[62*k,19.5*k];count=W<560?52:80;
    gs=[W*.82,st-ringR*.8-10];gz=-240;
    fs=[W*1.05,TOP+10];fz=-2300;
    ks=[gs[0]-12,st+36];kz=20;
  }
  if(level>1)count=Math.round(count*.55);
  cv.style.webkitMaskImage=cv.style.maskImage=mask;
  G=unproject(gs[0],gs[1],gz);C=unproject(fs[0],fs[1],fz);K=unproject(ks[0],ks[1],kz);
  A=norm([C[0]-G[0],C[1]-G[1],C[2]-G[2]]);B1=norm(cross(A,[0,1,0]));B2=cross(A,B1);
  gl.useProgram(prog);gl.uniform2f(U.uRes,W,H);gl.uniform2f(U.uFog,wide?700:520,wide?3300:2500);
}

// ---------- instances ----------
function axes(hx,hy,rx,ry,rz){
  var cz=Math.cos(rz),sz=Math.sin(rz),cx=Math.cos(rx),sx=Math.sin(rx),cy=Math.cos(ry),sy=Math.sin(ry);
  AX[0]=hx*(cz*cy+sz*sx*sy);AX[1]=hx*sz*cx;AX[2]=hx*(-cz*sy+sz*sx*cy);
  AY[0]=hy*(-sz*cy+cz*sx*sy);AY[1]=hy*cz*cx;AY[2]=hy*(sz*sy+cz*sx*cy);
}
function put(x,y,z,c,a,kind,seed,rev,light){
  if(n>=MAX)return -1;
  var o=n*STRIDE;
  buf[o]=x;buf[o+1]=y;buf[o+2]=z;
  buf[o+3]=AX[0];buf[o+4]=AX[1];buf[o+5]=AX[2];buf[o+6]=AY[0];buf[o+7]=AY[1];buf[o+8]=AY[2];
  buf[o+9]=c[0];buf[o+10]=c[1];buf[o+11]=c[2];buf[o+12]=a;
  buf[o+13]=kind;buf[o+14]=seed;buf[o+15]=rev;buf[o+16]=light;
  zs[n]=z;return n++;
}
function ss(a,b,x){x=(x-a)/(b-a);x=x<0?0:x>1?1:x;return x*x*(3-2*x)}
function hash(x){x=Math.sin(x*127.1)*43758.5453;return x-Math.floor(x)}

var PERIOD=16,GATE_AT=.8,POSE=[-.16,-.3,0],RING=[-.38,-.58];   // seconds per cycle; share of it spent approaching; pose at the gate
var mx=0,my=0,tx=0,ty=0,sc=0;
function draw(t){
  n=0;
  var cx=cam[0]-mx*44,cy=cam[1]-my*26+sc*.1;
  var flash=0,flashC=ACC,land=0,landC=ACT,i,o;
  // light behind the gate, the gate itself, and the glow where verdicts land on the terminal
  axes(ringR*4.4,ringR*4.4,0,0,0);put(G[0],G[1],G[2]-40,ACC,.2,5,0,0,0);
  axes(ringR*2.4,ringR*2.4,RING[0],RING[1],0);var ring=put(G[0],G[1],G[2],ACC,1,4,0,0,0);
  axes(aSize[0]*1.5,aSize[1]*2.6,0,0,0);var sink=put(K[0],K[1]-aSize[1],K[2]-20,ACT,0,5,0,0,0);
  for(i=0;i<count;i++){
    o=i*8;
    var ph=t/PERIOD+rnd[o],u=ph-Math.floor(ph),cyc=Math.floor(ph);
    var hv=hash(i*3.31+cyc*7.77),kind=hv<.05?3:hv<.15?2:1;
    var r2=Math.sqrt(rnd[o+2]),a0=rnd[o+3]*TAU;
    // where this card crosses the gate plane
    var ga=a0+3.1,gr=gateR*r2;
    var gx=G[0]+(B1[0]*Math.cos(ga)+B2[0]*Math.sin(ga))*gr,gy=G[1]+(B1[1]*Math.cos(ga)+B2[1]*Math.sin(ga))*gr,gz=G[2]+(B1[2]*Math.cos(ga)+B2[2]*Math.sin(ga))*gr;
    var tum1=rnd[o+4]*TAU+t*(.25+.5*rnd[o+5]),tum2=rnd[o+6]*TAU+t*(.2+.45*rnd[o+7]),sz=.86+.3*rnd[o+1];
    if(u<GATE_AT){
      // approach: a slow vortex that narrows into the gate
      var a=u/GATE_AT,e=Math.pow(a,1.2),len=(.72+.5*rnd[o+1])*(1-e),sp=Math.pow(1-e,1.35);
      var rad=(gateR+(srcR-gateR)*sp)*r2,an=a0+3.1*e,ca=Math.cos(an)*rad,sa=Math.sin(an)*rad;
      var dx=C[0]-G[0],dy=C[1]-G[1],dz=C[2]-G[2];
      var px=G[0]+dx*len+B1[0]*ca+B2[0]*sa,py=G[1]+dy*len+B1[1]*ca+B2[1]*sa,pz=G[2]+dz*len+B1[2]*ca+B2[2]*sa;
      var al=ss(.7,.985,a),fr=1-al;
      axes(uSize[0]*sz,uSize[1]*sz,POSE[0]*al+tum1*fr,POSE[1]*al+tum2*fr,(rnd[o+4]-.5)*.5*fr);
      put(px,py,pz,ACC,ss(0,.09,a),0,rnd[o+5],0,ss(.5,1,a));
    }else{
      var b=(u-GATE_AT)/(1-GATE_AT);
      if(kind>1){
        // watch or act: flip into a terminal row, pause, then drop into the terminal
        var f=b/.62;if(f>=1)continue;
        var col=kind>2?ACT:WATCH,g=f<.14?0:Math.pow((f-.14)/.86,1.7);
        var kx=K[0]+(rnd[o+5]-.5)*aSize[0]*.9,qx=(gx+kx)*.5,qy=gy+(K[1]-gy)*.2,qz=gz+(K[2]-gz)*.6+70;
        var h=1-g,x=h*h*gx+2*h*g*qx+g*g*kx,y=h*h*gy+2*h*g*qy+g*g*K[1],z=h*h*gz+2*h*g*qz+g*g*K[2];
        var fl=Math.PI*ss(0,.15,f),rev=fl>Math.PI/2?1:0,pop=1+.12*Math.sin(Math.PI*Math.min(1,f/.22));
        var k=.25*ss(.04,.16,f)+.75*ss(0,.7,g),hx=(uSize[0]*sz+(aSize[0]-uSize[0]*sz)*k)*pop,hy=(uSize[1]*sz+(aSize[1]-uSize[1]*sz)*k)*pop;
        axes(hx,hy,POSE[0]*(1-g*.6)+(rev?fl-Math.PI:fl),POSE[1]*(1-g)+(rnd[o+6]-.5)*.16*g,(rnd[o+7]-.5)*.1);
        put(x,y,z,col,1-ss(.86,1,g),kind,rnd[o+5],rev,0);
        axes(hx*1.7,hy*3,0,0,0);put(x,y,z-12,col,.3*rev*(1-g*.7),5,0,0,0);
        if(f<.3&&1-f/.3>flash){flash=1-f/.3;flashC=col}
        if(g>.72&&ss(.72,1,g)>land){land=ss(.72,1,g);landC=col}
      }else{
        // set aside: a ghost that falls away
        var f2=b/.8;if(f2>=1)continue;
        var side=wide||rnd[o+5]>.3?1:-1,vx=side*(.35+.75*rnd[o+6])*(side<0?.55:1),vy=.3+.5*rnd[o+7];
        var tw=ss(0,.35,f2);
        axes(uSize[0]*sz,uSize[1]*sz,POSE[0]+tum1*tw*.5,POSE[1]+tum2*tw*.5,side*f2*.6);
        put(gx+vx*f2*ringR*3.4,gy+vy*f2*ringR*1.6+f2*f2*ringR*2.6,gz-f2*ringR*4.5,ACC,Math.pow(1-f2,1.2),1,rnd[o+5],ss(0,.1,f2),0);
      }
    }
  }
  o=ring*STRIDE;buf[o+9]=flashC[0];buf[o+10]=flashC[1];buf[o+11]=flashC[2];buf[o+16]=flash*.28;
  o=sink*STRIDE;buf[o+9]=landC[0];buf[o+10]=landC[1];buf[o+11]=landC[2];buf[o+12]=land*.55;
  // painter's order: far to near
  ord.length=n;for(i=0;i<n;i++)ord[i]=i;
  ord.sort(function(p,q){return zs[p]-zs[q]});
  for(i=0;i<n;i++)out.set(buf.subarray(ord[i]*STRIDE,ord[i]*STRIDE+STRIDE),i*STRIDE);
  gl.useProgram(prog);gl.bindVertexArray(vao);
  gl.uniform3f(U.uCam,cx,cy,CAM_D);gl.uniform1f(U.uTime,t);
  gl.bindBuffer(gl.ARRAY_BUFFER,ibo);gl.bufferSubData(gl.ARRAY_BUFFER,0,out,0,n*STRIDE);
  gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,tex);
  gl.clear(gl.COLOR_BUFFER_BIT);
  gl.drawArraysInstanced(gl.TRIANGLE_STRIP,0,4,n);
}

// ---------- run loop ----------
var reduce=matchMedia("(prefers-reduced-motion:reduce)").matches;
var clock=44.25,last=0,raf=0,seen=true,ok=true,slow=0,frames=0;   // starts at a moment that shows the whole story, for the still frame
function still(){if(ok)draw(clock)}
function tick(ts){
  raf=0;
  if(!ok||!seen||document.hidden||reduce)return;
  var dt=last?ts-last:16;last=ts;
  clock+=Math.min(dt,60)/1000;
  mx+=(tx-mx)*.06;my+=(ty-my)*.06;
  draw(clock);
  // quality: step down once if the first second or two runs slowly; a third step leaves a still frame
  if(level<3&&++frames>12){slow+=dt;if(frames>=72){if(slow/60>34){level++;if(level>2){reduce=true}else layout()}frames=0;slow=0}}
  raf=requestAnimationFrame(tick);
}
function start(){last=0;frames=0;slow=0;if(!raf&&ok&&seen&&!document.hidden&&!reduce)raf=requestAnimationFrame(tick)}
function refresh(){if(!ok)return;layout();if(reduce||!raf)still();start()}

try{seedRandoms();setup();theme();layout();still()}catch(e){ok=false;cv.remove();return}
cv.classList.add("on");

if(document.fonts&&document.fonts.load)document.fonts.load('600 36px "IBM Plex Mono"').then(function(){if(ok){labels();still()}},function(){});
var rz=0;
function onResize(){clearTimeout(rz);rz=setTimeout(refresh,120)}
if("ResizeObserver" in window)new ResizeObserver(onResize).observe(hero);else addEventListener("resize",onResize);
if("IntersectionObserver" in window)new IntersectionObserver(function(es){seen=es[0].isIntersecting;start()}).observe(cv);
document.addEventListener("visibilitychange",start);
addEventListener("scroll",function(){sc=Math.min(window.scrollY||0,H);if(reduce)still()},{passive:true});
if(matchMedia("(hover:hover) and (pointer:fine)").matches)addEventListener("pointermove",function(e){tx=e.clientX/innerWidth*2-1;ty=e.clientY/innerHeight*2-1},{passive:true});
new MutationObserver(function(){theme();still()}).observe(root,{attributes:true,attributeFilter:["data-theme"]});
var mq=matchMedia("(prefers-color-scheme: dark)"),onScheme=function(){theme();still()};
if(mq.addEventListener)mq.addEventListener("change",onScheme);else if(mq.addListener)mq.addListener(onScheme);
cv.addEventListener("webglcontextlost",function(e){e.preventDefault();ok=false;if(raf){cancelAnimationFrame(raf);raf=0}});
cv.addEventListener("webglcontextrestored",function(){try{setup();theme();layout();ok=true;still();start()}catch(e){cv.remove()}});
start();
})();
