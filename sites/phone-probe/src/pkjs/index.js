/* Synthetic access probe. No Sites service credential or brokerage token. */
var url = "https://pebble-hood-connection-test.kvnsr1.chatgpt.site/probe.json";
var busy = false;
var pending = false;
var phase = "baseline";
function report(text) {
  Pebble.sendAppMessage({SUMMARY:text.slice(0,190)},function(){},function(){});
}
function request(withToken, callback) {
  var done=false, x=new XMLHttpRequest();
  function finish(state, status, marker) {
    if(done) return;
    done=true;
    callback({state:state,http:status||0,marker:!!marker});
  }
  x.open("GET",url,true);
  x.withCredentials=true;
  x.timeout=15000;
  if(withToken) x.setRequestHeader("Authorization","Bearer synthetic-pebble-view-token");
  x.onload=function(){
    var marker=false;
    try {marker=JSON.parse(x.responseText).kind==="pebble-hood-sites-probe";}catch(_){}
    finish(x.status===401?"SIGN_IN_REQUIRED":marker?"JSON_OK":"OTHER_RESPONSE",x.status,marker);
  };
  x.onerror=function(){finish("NETWORK_OR_PERMISSION",x.status,false);};
  x.ontimeout=function(){finish("TIMEOUT",0,false);};
  try{x.send();}catch(_){finish("NETWORK_OR_PERMISSION",0,false);}
}
function run() {
  if(busy) {pending=true;return;}
  busy=true;
  var requestPhase=phase;
  report("Testing phone access...\n\nDemo only.");
  request(false,function(anonymous){
    request(true,function(view){
      var result={phase:requestPhase,without_extra_header:anonymous,view_token:view};
      console.log("SITES_TEST_RESULT "+JSON.stringify(result));
      var label=anonymous.marker||view.marker?"JSON reached":anonymous.http===401&&view.http===401?"Sign-in required":anonymous.http===0||view.http===0?"Network/permission":"Unexpected response";
      report("Standard: "+anonymous.http+"\nView token: "+view.http+"\n\n"+label+"\nDemo only. Select retries.");
      busy=false;
      if(pending) {pending=false;run();}
    });
  });
}
Pebble.addEventListener("ready",function(){setTimeout(run,2000);});
Pebble.addEventListener("appmessage",run);
Pebble.addEventListener("showConfiguration",function(){
  Pebble.openURL("https://pebble-hood-connection-test.kvnsr1.chatgpt.site/");
});
Pebble.addEventListener("webviewclosed",function(e){
  if(e.response==="sites-cookie-probe") {phase="after_chatgpt_signin";run();}
});
