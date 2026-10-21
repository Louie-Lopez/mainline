const branchText={
  en:{title:'Mainline — branch experiment',home:'← Mainline',return:'Return to project mainline',path:'Current location',picker:'Choose a branch',current:'Viewing',exploring:'Exploring',count:n=>n+' branches',open:(parent,n)=>parent+', view '+n+' branches',route:name=>'Branch · '+name,switch:name=>'Current branch: '+name+', switch branch'},
  zh:{title:'Mainline · 支线实验',home:'← 主线',return:'返回项目主线',path:'当前位置',picker:'选择支线',current:'当前查看',exploring:'探索中',count:n=>n+' 条支线',open:(parent,n)=>parent+'，查看 '+n+' 条支线',route:name=>'支线 · '+name,switch:name=>'当前支线：'+name+'，切换支线'}
}[language];
const experiment=branchSamples[language];
document.title=branchText.title;
document.getElementById('route-path').setAttribute('aria-label',branchText.path);
document.getElementById('branch-picker').setAttribute('aria-label',branchText.picker);

// Branches are explicit sample routes. No background work or project writes.
const routePath=document.getElementById('route-path');
const picker=document.getElementById('branch-picker');
const routeViews=new Map();
let route='main',pickerAnchor=null;
const branchById=id=>experiment.branches.find(branch=>branch.id===id);
const validRoute=id=>branchById(id)?id:'main';
const routeFromUrl=()=>validRoute(location.hash.slice(1));

function closePicker(restoreFocus=false){
  picker.hidden=true;
  pickerAnchor?.setAttribute('aria-expanded','false');
  if(restoreFocus&&pickerAnchor?.isConnected)pickerAnchor.focus({preventScroll:true});
  pickerAnchor=null;
}

function openPicker(anchor,parent){
  if(!picker.hidden&&pickerAnchor===anchor){closePicker(true);return;}
  closePicker();
  pickerAnchor=anchor;
  picker.replaceChildren();
  for(const branch of experiment.branches.filter(item=>item.parent===parent)){
    const button=document.createElement('button');
    button.type='button';button.className='branch-choice';
    button.dataset.route=branch.id;
    const name=document.createElement('span');name.textContent=branch.name;
    const state=document.createElement('small');state.textContent=route===branch.id?branchText.current:branchText.exploring;
    button.append(name,state);
    if(route===branch.id)button.setAttribute('aria-current','true');
    button.onclick=()=>navigate(branch.id);
    picker.append(button);
  }
  anchor.setAttribute('aria-expanded','true');
  picker.hidden=false;
  const rect=anchor.getBoundingClientRect();
  const width=picker.offsetWidth,height=picker.offsetHeight;
  picker.style.left=Math.max(16,Math.min(window.innerWidth-width-16,rect.left+rect.width/2-width/2))+'px';
  const preferredTop=rect.bottom+8;
  picker.style.top=Math.max(16,preferredTop+height<window.innerHeight-16?preferredTop:rect.top-height-8)+'px';
  (picker.querySelector('[aria-current]')||picker.querySelector('button'))?.focus({preventScroll:true});
}

function chooserButton(label,parent,className){
  const button=document.createElement('button');button.type='button';
  button.className=className;
  const icon=document.createElementNS('http://www.w3.org/2000/svg','svg');
  icon.setAttribute('viewBox','0 0 16 16');icon.setAttribute('aria-hidden','true');
  const path=document.createElementNS('http://www.w3.org/2000/svg','path');
  path.setAttribute('d','M4 3v10M4 9c0-4 8-2 8-6M2 3h4M2 13h4M10 3h4');icon.append(path);
  const name=document.createElement('span');name.textContent=label;
  const chevron=document.createElement('span');chevron.className='branch-chevron';chevron.textContent='⌄';chevron.setAttribute('aria-hidden','true');
  button.append(icon,name,chevron);
  button.setAttribute('aria-haspopup','dialog');button.setAttribute('aria-expanded','false');
  button.setAttribute('aria-controls','branch-picker');
  button.onclick=()=>openPicker(button,parent);
  return button;
}

function renderBranchChrome(){
  closePicker();routePath.replaceChildren();routePath.hidden=route==='main';
  if(route==='main'){
    for(const parent of new Set(experiment.branches.map(branch=>branch.parent))){
      const stage=[...axis.children].find(li=>li.querySelector(':scope > .node')?.dataset.stage===parent);
      if(!stage)continue;
      const count=experiment.branches.filter(branch=>branch.parent===parent).length;
      const button=chooserButton(branchText.count(count),parent,'branch-access');
      button.setAttribute('aria-label',branchText.open(parent,count));
      stage.append(button);
    }
    return;
  }
  const branch=branchById(route);
  const home=document.createElement('button');home.type='button';home.className='route-home';
  home.textContent=branchText.home;home.setAttribute('aria-label',branchText.return);home.onclick=()=>navigate('main');
  const separator=document.createElement('span');separator.className='route-separator';separator.textContent='›';separator.setAttribute('aria-hidden','true');
  const parent=document.createElement('span');parent.textContent=branch.parent;
  const next=separator.cloneNode(true);
  const choices=chooserButton(branchText.route(branch.name),branch.parent,'route-switch');
  choices.setAttribute('aria-label',branchText.switch(branch.name));
  routePath.append(home,separator,parent,next,choices);
}

function showRoute(id,moveFocus=false){
  routeViews.set(route,{selected,expanded});
  route=validRoute(id);
  const view=routeViews.get(route);
  selected=view?.selected??null;expanded=view?.expanded??null;
  const branch=branchById(route);
  const state=branch?{...branch,task_id:experiment.project.task_id}:experiment.project;
  render(state,true);axis.dataset.stale='false';
  if(moveFocus){
    const target=branch?routePath.querySelector('.route-switch'):axis.querySelector('.branch-access');
    target?.focus({preventScroll:true});
  }
}

function navigate(id){
  const next=validRoute(id);
  if(next===route){closePicker(true);return;}
  history.pushState(null,'',location.pathname+location.search+(next==='main'?'':'#'+next));
  showRoute(next,true);
}

document.addEventListener('pointerdown',event=>{
  if(!picker.hidden&&!picker.contains(event.target)&&!pickerAnchor?.contains(event.target))closePicker();
});
document.addEventListener('keydown',event=>{
  if(picker.hidden)return;
  if(event.key==='Escape'){event.preventDefault();closePicker(true);return;}
  const buttons=[...picker.querySelectorAll('button')];
  if(event.key==='ArrowDown'||event.key==='ArrowUp'){
    event.preventDefault();
    const offset=event.key==='ArrowDown'?1:-1;
    buttons[(buttons.indexOf(document.activeElement)+offset+buttons.length)%buttons.length]?.focus();
  }
});
document.addEventListener('focusin',event=>{
  if(!picker.hidden&&!picker.contains(event.target)&&event.target!==pickerAnchor)closePicker();
});
window.addEventListener('resize',()=>closePicker());
window.addEventListener('scroll',()=>closePicker(),{passive:true});
window.addEventListener('popstate',()=>showRoute(routeFromUrl()));
showRoute(routeFromUrl());
