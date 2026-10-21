const experiment=branchSamples[language];
document.title=language==='zh'?'Mainline · 支线演示':'Mainline — branch demo';
const branches=Object.fromEntries(experiment.branches.map(({id,...branch})=>[id,branch]));
render({...experiment.project,branches});
axis.dataset.stale='false';
