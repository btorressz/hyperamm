const {test}=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');

const root=process.env.TERMINAL_TEST_BUILD;
const h=require(path.join(root,'utils/terminalHistory.js'));
const chart=require(path.join(root,'components/HistoryChart.js'));

const origin='2026-11-11T10:11:12';
const at=micro=>origin+'.'+String(micro).padStart(6,'0')+'Z';

function legacyLookup(points,axis,key){
  const displayed=axis==='frame'?points:h.boundedObservations(points,1000);
  return [...displayed].reverse().find(p=>axis==='frame'
    ?p.sequence===key:Math.floor(Date.parse(p.timestamp)/1000)===key);
}

test('time lookup preserves last observation of a second and microsecond identity',()=>{
  const points=[
    {sequence:1,timestamp:at(12),equity:'1.1'},
    {sequence:2,timestamp:at(13),equity:'1.2'},
    {sequence:3,timestamp:'2026-11-11T10:11:13.000001Z',equity:'1.3'},
  ];
  const index=h.chartObservationIndex(points,'time');
  const second=Math.floor(Date.parse(points[0].timestamp)/1000);
  assert.equal(index.size,2);
  assert.equal(index.get(second).sequence,2);
  assert.deepEqual(index.get(second),legacyLookup(points,'time',second));
  assert.equal(index.get(second+1).sequence,3);
  assert.equal(points.length,3);
});

test('frame index never buckets separate same-second frames',()=>{
  const points=[
    {sequence:2,timestamp:at(10),session_pnl:'0'},
    {sequence:3,timestamp:at(20),session_pnl:'1'},
    {sequence:3,timestamp:at(21),session_pnl:'2'},
  ];
  const index=h.chartObservationIndex(points,'frame');
  assert.equal(index.size,2);
  assert.equal(index.get(3).session_pnl,'2');
  assert.deepEqual(index.get(3),legacyLookup(points,'frame',3));
});

test('bounded time lookup matches old scan for larger unsorted inputs',()=>{
  const points=Array.from({length:1600},(_,i)=>({
    sequence:i+1,
    timestamp:new Date(Date.UTC(2026,10,11,0,0,i%60)).toISOString(),
    equity:String(i),
  }));
  const expected=h.boundedObservations(points,1000);
  const index=h.chartObservationIndex(points,'time');
  assert.equal(index.size,expected.length);
  for(const p of expected){
    const key=Math.floor(Date.parse(p.timestamp)/1000);
    assert.deepEqual(index.get(key),legacyLookup(points,'time',key));
  }
});

test('invalid timestamps do not produce lookup keys; chart data stays separate',()=>{
  const points=[
    {sequence:1,timestamp:'invalid',equity:null},
    {sequence:2,timestamp:'2026-11-11T10:11:12Z',equity:'1'},
  ];
  const index=h.chartObservationIndex(points,'time');
  assert.equal(index.has(NaN),false);
  assert.equal(index.size,1);
  const lines={key:'equity',label:'Equity',color:'#ffffff'};
  const plotted=chart.seriesCoordinates(points,lines,'frame');
  assert.deepEqual(plotted.map(p=>p.time),[1,2]);
  assert.equal(plotted[0].value,null);
  assert.equal(plotted[1].value,1);
});

test('existing gap rendering does not connect missing points',()=>{
  const groups=chart.contiguousSegments([
    {time:1,value:0},{time:2,value:null},{time:3,value:1},
    {time:4,value:null},{time:5,value:2},
  ]);
  assert.deepEqual(groups,[
    [{time:1,value:0}],[{time:3,value:1}],[{time:5,value:2}],
  ]);
});
