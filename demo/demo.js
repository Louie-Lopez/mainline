
const demoMessages={
  en:{title:'Mainline — interactive demo',hint:'Select a stage to explore. Switch examples to see progress change.',note:'Sample project · No installation · No AI connection',install:'Use Mainline in your project →',scenarios:'Example progress',nav:'Language and source',steps:['Starting','Parallel work','Fixing','Delivered'],goal:'Help people keep their whole project in view while working with AI.',names:['Define','Design','Build','Try','Share'],goals:['Agree on the problem and what a useful result looks like.','Keep the project view clear with as little interface as possible.','Turn the agreed design into a working tool.','Find out whether the tool helps during real projects.','Make the tool easy for other people to try and use.'],details:['A stable project goal and a few stages from start to finish.','One sentence, one axis, and details only when needed.','A local record, a responsive view, and instructions for the assistant.','Try it in a real project for a few days.\n\n1. Return to the project and check where it stands.\n2. Note what helped or got in the way.\n3. Decide whether to keep using it.','A public repository, a simple demo, and clear installation instructions.'],children:['Record','View','Instructions'],childGoals:['Keep project scope and progress in one local record.','Make current work visible at a glance.','Update only when meaningful progress changes.'],childDetails:['Keep stages stable while their statuses change.','Adapt the axis to the window and reveal one group of substages at a time.','The assistant records progress; viewing the page does not call a model.'],fix:'Fixing',verify:'Verifying'},
  zh:{title:'Mainline — 交互演示',hint:'点击环节查看细节，切换下方示例体验进展变化。',note:'示例项目 · 无需安装 · 不连接 AI 或你的项目',install:'在你的项目中使用 Mainline →',scenarios:'示例进展',nav:'语言与源码',steps:['开始','并行推进','修复错误','已交付'],goal:'帮助人们在和 AI 工作时，始终看得见整个项目。',names:['明确需求','设计方案','实现工具','实际试用','分享使用'],goals:['明确要解决的问题，以及怎样才算做好。','用尽可能少的界面，让项目全景清晰可见。','把约定的方案做成可用工具。','在真实项目中验证工具是否有帮助。','让其他人容易体验和使用这个工具。'],details:['确定稳定的项目目标，以及从开始到完成的几个阶段。','一句话、一条轴，需要时再展开细节。','保存本地记录，展示自适应视图，提供 AI 操作说明。','放进真实项目里用几天。\n\n1. 隔天回来，看看能否快速接上进度。\n2. 记录帮上忙或造成负担的地方。\n3. 再决定是否继续使用。','提供公开仓库、简洁演示和清晰的安装说明。'],children:['状态记录','页面展示','操作规则'],childGoals:['用一份本地记录保留项目范围和进度。','让当前工作一眼可见。','只在进展有意义地变化时更新。'],childDetails:['阶段保持稳定，工作推进时改变状态。','随窗口宽度调整轴的方向，一次只展开一组子环节。','AI 明确记录进展；查看页面不会调用模型。'],fix:'修复错误',verify:'验证结果'}
};
const demo=demoMessages[language];
document.title=demo.title;
document.getElementById('hint').textContent=demo.hint;
document.getElementById('demo-note').textContent=demo.note;
const about=document.getElementById('about');
about.textContent=language==='zh'?'关于':'About';
about.href='support.html?lang='+language;
document.querySelector('.topbar nav').setAttribute('aria-label',demo.nav);
const install=document.getElementById('install');
install.textContent=demo.install;
install.href='https://github.com/Louie-Lopez/mainline'+(language==='zh'?'/blob/main/README.zh-CN.md#安装':'#install');
document.getElementById('lang-'+language).setAttribute('aria-current','true');
const scenarios=document.getElementById('scenarios');
scenarios.setAttribute('aria-label',demo.scenarios);
const requestedStep=Number(new URLSearchParams(location.search).get('step')??1);
let scenario=Number.isInteger(requestedStep)&&requestedStep>=0&&requestedStep<=3?requestedStep:1;
const mapping=(names,values)=>Object.fromEntries(names.map((name,index)=>[name,values[index]]));
function showScenario(index){
  scenario=index;selected=null;expanded=null;
  const status=index===0?['active','pending','pending','pending','pending']:index===3?Array(5).fill('done'):['done','done','active','active','pending'];
  const childStatus=index===0?Array(3).fill('pending'):index===3?Array(3).fill('done'):['done','active','done'];
  const labels=index===2?{[demo.names[2]]:demo.fix,[demo.names[3]]:demo.verify}:{};
  render({task_id:'public-demo',mainline:demo.goal,stages:demo.names,stage_statuses:status,stage_labels:labels,stage_mainlines:mapping(demo.names,demo.goals),stage_details:mapping(demo.names,demo.details),substages:{[demo.names[2]]:{stages:demo.children,stage_statuses:childStatus,stage_labels:index===2?{[demo.children[1]]:demo.fix}:{},stage_mainlines:mapping(demo.children,demo.childGoals),stage_details:mapping(demo.children,demo.childDetails)}}},true);
  axis.dataset.stale='false';
  [...scenarios.children].forEach((button,i)=>button.setAttribute('aria-pressed',String(i===index)));
  for(const lang of ['en','zh'])document.getElementById('lang-'+lang).href='?lang='+lang+'&step='+index;
  const url=new URL(location.href);url.searchParams.set('step',index);history.replaceState(null,'',url);
}
demo.steps.forEach((name,index)=>{const button=document.createElement('button');button.type='button';button.textContent=name;button.onclick=()=>showScenario(index);scenarios.append(button);});
showScenario(scenario);
