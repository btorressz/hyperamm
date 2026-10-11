const path=require('node:path');
const compiled=process.env.TERMINAL_TEST_BUILD;
const load=p=>require(path.join(compiled,p));
const raw=require('./phase153-fixtures.json');
function fixture(market='BTC',kind='snapshot') {
  const value=structuredClone(raw[market][kind]);
  const latest=Math.max(...['BTC','ETH','SOL'].map(m=>Date.parse(raw[m].envelope.emitted_at)));
  const delta=Date.now()-latest-100;
  function shift(o){for(const [key,v] of Object.entries(o)){
    if(typeof v==='string' && /^\d{4}-\d\d-\d\dT/.test(v))o[key]=new Date(Date.parse(v)+delta).toISOString();
    else if(v&&typeof v==='object')shift(v);
  }}
  shift(value);return value;
}
module.exports={load,fixture,raw};
