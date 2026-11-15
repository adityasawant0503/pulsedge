// Where a visitor first came from, as one short word: "instagram", "telegram", "google", ... or "direct".
// Sign-up, waitlist and payment forms send it as `via`, so Instagram sign-ups can be told apart.
// Read from, in order: ?utm_source= in the link, the Instagram or Facebook in-app browser, the site that linked here.
// Only the word is kept (in this browser, under "pe_src"), never the full address of the page they came from.
(function(){
  var KEY="pe_src",SITES=[[/(^|\.)instagram\.com$/,"instagram"],[/(^|\.)(t\.me|telegram\.(org|me))$/,"telegram"],[/(^|\.)(linkedin\.com|lnkd\.in)$/,"linkedin"],
    [/(^|\.)(youtube\.com|youtu\.be)$/,"youtube"],[/(^|\.)(x\.com|twitter\.com|t\.co)$/,"x"],[/(^|\.)(facebook\.com|fb\.me)$/,"facebook"],
    [/(^|\.)whatsapp\.com$/,"whatsapp"],[/(^|\.)google\.[a-z.]+$/,"google"]];
  function clean(s){return String(s||"").toLowerCase().replace(/[^a-z0-9._-]/g,"").slice(0,24)}
  function detect(){
    var q=location.search.match(/[?&]utm_source=([^&#]*)/),tag="";
    try{tag=clean(q&&decodeURIComponent(q[1]))}catch(e){}
    if(tag)return tag;
    var ua=navigator.userAgent||"";
    if(/Instagram/i.test(ua))return "instagram";
    if(/FBAN|FBAV/.test(ua))return "facebook";
    var host="";try{host=new URL(document.referrer).hostname.toLowerCase()}catch(e){}
    if(!host||host===location.hostname)return "";
    for(var i=0;i<SITES.length;i++)if(SITES[i][0].test(host))return SITES[i][1];
    return clean(host.replace(/^www\./,""));
  }
  var src="";
  try{src=clean(localStorage.getItem(KEY))}catch(e){}
  if(!src){src=detect();if(src){try{localStorage.setItem(KEY,src)}catch(e){}}}
  window.PulseSource=src||"direct";
})();
