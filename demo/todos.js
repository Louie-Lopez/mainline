// Demo interactions affect only this page's fictional state, never a local project.
async function saveTodo(payload){
  const state=structuredClone(projectState);
  let group=payload.branch?state.branches[payload.branch]:state;
  if(payload.parent)group=group.substages[payload.parent];
  const item=group.stage_todos[payload.stage].items.find(item=>item.id===payload.id);
  if(!item)throw Error('save');
  item.done=payload.done;
  if(Number.isInteger(state.revision))state.revision++;
  return state;
}
async function refresh(){render(projectState,true);}
