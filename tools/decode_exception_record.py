"""Decode/validate v1/v2 preopened exception records; stdlib only, no game data."""
import argparse,json,struct
from pathlib import Path
MAGIC=0x31304358454947
END=0x31444e4558434947
NAMES=['magic','version','bytes','context_present','run_tick','crash_tick','host_base','guest_base','guest_size','error_desc','pstate','esr','afsr0','afsr1','aarch64','pc','lr','sp','fp','far']+[f'x{i}' for i in range(29)]
def decode(data):
 if len(data)<456:raise ValueError('truncated record')
 fields=struct.unpack_from('<49Q48s',data)
 out=dict(zip(NAMES,fields[:49]));build=fields[49]
 version=out['version'];length={1:456,2:600}.get(version)
 if length is None or out['magic']!=MAGIC or out['bytes']!=length:raise ValueError('unrecognized record layout')
 if len(data)<length:raise ValueError('truncated record')
 checksum,end=struct.unpack_from('<QQ',data,length-16)
 if end!=END:raise ValueError('unrecognized record layout')
 if version==2:
  names=['schema','memalign_calls','primary_failures','final_failures','first_state','first_request','first_alignment','first_caller','first_primary_errno','first_final_errno','cache_valid','manager','manager_flags','default_allocator','shared_allocator','label9_allocator','debug_overhead','cache_generation']
  out['allocation']=dict(zip(names,struct.unpack_from('<18Q',data,440)))
  observation=out['allocation']
  if observation['schema'] not in (0,1) or observation['first_state'] not in (0,1,2) or observation['cache_valid'] not in (0,1):raise ValueError('unrecognized allocation observation state')
 value=14695981039346656037
 for byte in data[:length-16]:value=((value^byte)*1099511628211)&0xffffffffffffffff
 if value!=checksum:raise ValueError('checksum mismatch: incomplete/corrupted write')
 if out['context_present'] not in (0,1):raise ValueError('invalid context state')
 out['build']=build.split(b'\0',1)[0].decode('ascii');out['status']='exception captured' if out['context_present'] else 'armed: no exception persisted'
 for name in ['pc','lr','sp','fp','far']:
  address=out[name]
  if out['guest_base'] and out['guest_base']<=address<out['guest_base']+out['guest_size']:out[name+'_relative']='guest+'+hex(address-out['guest_base'])
  elif out['host_base'] and out['host_base']<=address<out['host_base']+0x1700000:out[name+'_relative']='host+'+hex(address-out['host_base'])+' (range heuristic; verify against ELF)'
 return out
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('record',type=Path);args=p.parse_args()
 try:result=decode(args.record.read_bytes())
 except (OSError,ValueError,UnicodeError) as error:p.exit(1,str(error)+'\n')
 print(json.dumps(result,indent=2))

