import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,beforeEach,expect,test,vi} from 'vitest';
import {request} from '../api';
import {MLObservatory} from './MLObservatory';
vi.mock('../api',()=>({request:vi.fn()}));
vi.mock('./MLRoutingReplay',()=>({MLRoutingReplay:()=>null}));
const call=vi.mocked(request);
beforeEach(()=>{call.mockReset();});
afterEach(cleanup);

test('missing training artifacts never render invented comparison scores',async()=>{
  call.mockResolvedValue({status:'not_trained',models:[],cases:[],message:'No evaluated run exists',source_url:'https://www.kaggle.com'});
  render(<MLObservatory/>);
  expect(await screen.findByText('No trained result published yet')).toBeInTheDocument();
  expect(screen.queryByText('Model comparison')).not.toBeInTheDocument();
});

test('transport failure is visible and never replaced with demonstration metrics',async()=>{
  call.mockRejectedValue(new Error('Service unavailable'));
  render(<MLObservatory/>);
  expect(await screen.findByRole('alert')).toHaveTextContent('Service unavailable');
  expect(screen.queryByText('Model comparison')).not.toBeInTheDocument();
});

test('inference is explicitly requested and a failure cannot appear as a fresh prediction',async()=>{
  // Unit-only fixture, unrelated to the published benchmark.
  const metrics={auroc:.5,auprc:.5,recall:.5,f1:.5,brier:.25,ece:.1,prevalence:.5,samples:2,reliability_bins:[]};
  call.mockResolvedValueOnce({status:'evaluated',source_url:'https://www.kaggle.com',coverage:'US',models:[{id:'fixture',name:'Fixture model',calibrated:metrics,uncalibrated:metrics,seconds:1}],cases:[{id:'case-fixture',label:0,reference_date:'2024-06-01'}]})
    .mockResolvedValueOnce({id:'case-fixture',label:0,reference_date:'2024-06-01',latitude:34,longitude:-118,variables:['vpd'],dates:[],sequence:Array.from({length:60},()=>[1]),predictions:{fixture:.5}})
    .mockRejectedValueOnce(new Error('Model inference is unavailable'));
  render(<MLObservatory/>);
  const button=await screen.findByRole('button',{name:/Run all three models/});
  fireEvent.click(button);
  await waitFor(()=>expect(call).toHaveBeenLastCalledWith('/api/v1/ml/cases/case-fixture/infer',{method:'POST'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Model inference is unavailable');
  expect(screen.queryByText(/Fresh CPU inference/)).not.toBeInTheDocument();
});
