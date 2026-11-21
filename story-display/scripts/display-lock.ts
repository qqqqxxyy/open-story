import { open, readFile, unlink, mkdir } from 'node:fs/promises';
import { join } from 'node:path';

/** Serialize snapshot + HTML + marker publication; recover only a dead owner. */
export async function withDisplayLock<T>(root: string, action: () => Promise<T>): Promise<T> {
  await mkdir(root,{recursive:true});
  const path = join(root,'.display.lock');
  const deadline = Date.now()+10_000;
  for (;;) {
    try {
      const handle = await open(path,'wx');
      await handle.writeFile(String(process.pid));
      await handle.close();
      break;
    } catch (error: any) {
      if (error.code !== 'EEXIST') throw error;
      const pid = Number(await readFile(path,'utf8').catch(()=>''));
      if (Number.isInteger(pid) && pid>0) {
        try { process.kill(pid,0); }
        catch (error: any) { if (error.code === 'ESRCH') { await unlink(path).catch(()=>{}); continue; } }
      }
      if (Date.now()>deadline) throw new Error('展示页正在发布，请稍后重试');
      await new Promise(resolve=>setTimeout(resolve,100));
    }
  }
  try { return await action(); } finally { await unlink(path); }
}
