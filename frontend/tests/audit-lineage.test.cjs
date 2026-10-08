const { test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { boundedObservations, mergeHistory, needsFit } = require(path.join(process.env.TERMINAL_TEST_BUILD, 'utils/terminalHistory.js'));
const { authorizationLineage } = require(path.join(process.env.TERMINAL_TEST_BUILD, 'utils/authorizationLineage.js'));
const point = sequence => ({ sequence, timestamp: new Date(1700000000000 + sequence * 1000).toISOString(), mid_price: sequence });
const state = { session: 'new', range: 'session', points: [111,112,113].map(point) };
const history = { session_id: 'new', range: 'session', points: Array.from({length: 11}, (_, i) => point(100+i)) };
test('late 100–110 GET preserves live 111–113, deduplicates and stays bounded', () => {
 const merged = mergeHistory(state, history, 1000);
 assert.deepEqual(merged.points.map(p => p.sequence), Array.from({length:14},(_,i)=>100+i));
 assert.deepEqual(mergeHistory(merged, history, 1000), merged);
 assert.deepEqual(mergeHistory(state, history, 3).points.map(p=>p.sequence),[111,112,113]);
 assert.equal(boundedObservations(Array.from({length:1200},(_,i)=>point(i)),1000).length,1000);
});
test('backend sequence outranks timestamp collisions and older duplicates', () => {
 const newer = { ...point(113), timestamp: point(110).timestamp };
 assert.deepEqual(boundedObservations([newer,point(110), newer],100),[newer]);
});
test('old session and old range responses are ignored', () => {
 assert.equal(mergeHistory(state,{...history,session_id:'old'},1000),state);
 assert.equal(mergeHistory(state,{...history,range:'1m'},1000),state);
});
test('initial/session/range fit only, never ordinary background refresh', () => {
 assert.equal(needsFit(null,'new:session',true),true);
 assert.equal(needsFit('new:session','new:session',true),false);
 assert.equal(needsFit('new:session','new:1m',true),true);
 assert.equal(needsFit('old:session','new:session',true),true);
 assert.equal(needsFit(null,'new:session',false),false);
});
const q = {side:'BID',level_index:1};
const terminal = { authorized_quotes:[q],risk_authorization:{authorized:true,authorized_quote_count:1,quote_fingerprint:'backend-ladder',authorization_fingerprint:'backend-envelope'}};
test('authorized slot uses backend ladder and envelope identity', () => {
 assert.deepEqual(authorizationLineage(terminal,q),{status:'AUTHORIZED',final:q,ladder:'backend-ladder',envelope:'backend-envelope'});
});
test('suppressed or blocked level never claims an envelope', () => {
 for (const t of [{...terminal,authorized_quotes:[]},{...terminal,risk_authorization:{...terminal.risk_authorization,authorized:false}}]) {
 assert.deepEqual(authorizationLineage(t,q),{status:'SUPPRESSED / NOT AUTHORIZED'});
 }
});
test('count mismatch or missing proof exposes unavailable lineage', () => {
 for (const changes of [{authorized_quote_count:2},{quote_fingerprint:undefined}])
 assert.deepEqual(authorizationLineage({...terminal,risk_authorization:{...terminal.risk_authorization,...changes}},q),{status:'INCONSISTENT / UNAVAILABLE LINEAGE'});
});
