import { Component } from 'react';
import type { ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App.tsx';
import '@xyflow/react/dist/style.css';
import './styles.css';
import { startAutoRefresh } from './auto-refresh.ts';
class Boundary extends Component<{children:ReactNode},{error:string}> {
  state={error:''};
  static getDerivedStateFromError(error:Error) {return {error:error.message};}
  render(){return this.state.error ? <div className="fatal"><h1>页面暂时无法打开</h1><p>{this.state.error}</p><p>请重新运行生成脚本，并查看终端中的数据提示。</p></div> : this.props.children;}
}
const bundle = JSON.parse(document.getElementById('story-data')!.textContent!);
createRoot(document.getElementById('root')!).render(<Boundary>{bundle.stories.length ? <App bundle={bundle}/> : <div className="fatal"><h1>暂无已发表内容</h1><p>故事发布新的一幕后，此页会自动更新。</p></div>}</Boundary>);
const storyVersions = JSON.parse(document.getElementById('story-display-versions')?.textContent ?? '{}');
startAutoRefresh(document.querySelector<HTMLMetaElement>('meta[name="story-display-revision"]')?.content ?? '',storyVersions);
