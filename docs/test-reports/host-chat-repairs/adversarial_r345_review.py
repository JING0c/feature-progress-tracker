"""Independent R3/R4/R5 review; all project mutations target temporary workspaces.
Run from repo: python3 -B docs/test-reports/host-chat-repairs/adversarial_r345_review.py
"""
from pathlib import Path
import copy, json, re, sys, tempfile, unittest
ROOT = Path(sys.argv.pop(1) if len(sys.argv) > 1 and not sys.argv[1].startswith('-') else Path(__file__).resolve().parents[3])
sys.path.insert(0, str(ROOT/'scripts'))
from plugin_mcp import call_tool
from planning_editor import editable_table, replace_features
from serve_dashboard import parse, flatten, summarize, RequestError
BASE='''# 临时订单项目规划书
## 项目目标与场景
帮助店员维护本地订单并导出订单清单。
## 范围与边界
本期仅管理本机订单，不包含在线支付。
## 功能规划与验收
| 编号 | 上级编号 | 功能名称 | 说明 | 验收标准 | 依赖 | 采用 |
|---|---|---|---|---|---|---|
| F01 | 无 | 订单管理 | 维护本地订单信息 | 可新增并找到订单 | 无 | 是 |
| F02 | 无 | 导出订单 | 下载订单清单文件 | 文件可打开且含订单记录 | 无 | 是 |
'''
REVIEW={'reviewer':'independent-review-fixture','score':94,'conclusion':'通过','evidence':'fixture assertions passed','reason':'隔离测试用独立审核资料'}
def add(key,parent,name,dep='无'):
    return {'key':key,'parent':parent,'功能名称':name,'说明':name+'操作仅作用于本机测试数据','验收标准':name+'后读回的数据与输入一致','依赖':dep}
class F:
    def __init__(self,root,plan=BASE):
        self.workspace=str(Path(root)/'ws')
        self.p=call_tool('create_project',{'workspace':self.workspace,'name':'临时独立审核'},'codex')['project']
        self.save_plan(plan)
    def call(self,name,**p):
        return call_tool(name,dict(workspace=self.workspace,project_id=self.p['id'],**p),'codex')
    def read(self): return self.call('read_project')
    def save_plan(self,content): return self.call('save_plan',revision=self.read()['plan']['revision'],content=content)
    def edit(self,**args): return self.call('edit_features',revision=self.read()['plan']['revision'],**args)
    def commit(self,preview): return self.call('save_plan',revision=preview['revision'],content=preview['content'])
    def candidate(self): return self.call('generate_ledger')
    def save_candidate(self,c,**overrides):
        payload=dict(content=c['content'],revision=c['ledger_revision'],plan_revision=c['plan_revision'],source_revision=c['source_revision']);payload.update(overrides)
        return self.call('save_ledger',**payload)
    def ledger(self): return self.save_candidate(self.candidate())
    def items(self): return {i['id']:i for g in parse(self.read()['ledger']['content']) for i in flatten(g['items'])}
    def progress(self,identity,changes,review=None):
        p=dict(feature_id=identity,revision=self.read()['ledger']['revision'],changes=changes)
        if review is not None:p['review']=review
        return self.call('update_feature_progress',**p)
    def accept(self,identity): return self.progress(identity,{'状态':'已完成','执行 Agent':'implementer-fixture','实现证据':'fixture local assertions'},REVIEW)
    def set_choices(self,choices):
        doc=self.read()['plan']['content'];rows=editable_table(doc)['rows']
        for row in rows:
            if row['编号'] in choices:row['采用']='是' if choices[row['编号']] else '否'
        return self.save_plan(replace_features(doc,rows))
class IndependentReview(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='independent-r345-');self.addCleanup(self.tmp.cleanup)
        self.f=F(self.tmp.name)
    def tree(self):
        f=self.f
        p=f.edit(additions=[add('N3','N2','写入明细'),add('N2','N1','订单明细'),add('N1','F01','保存订单'),add('N4','F01','搜索订单')],updates=[{'id':'F02','fields':{'依赖':'N3'}}])
        f.commit(p);f.ledger();return p['mapping']
    def assert_rejected_unchanged(self,fn):
        before=self.f.read()
        with self.assertRaises((ValueError,RuntimeError,OSError,RequestError)) as caught:fn()
        after=self.f.read()
        self.assertEqual(before['plan']['revision'],after['plan']['revision'])
        self.assertEqual(before['ledger']['revision'],after['ledger']['revision'])
        return str(caught.exception)
    def test_end_to_end_new_tree_suggestions_preview_save_ledger_progress(self):
        f=self.f;m=self.tree();base=f.read()
        s=f.call('record_suggestions',revision=base['plan']['revision'],analyst='independent fixture analyst',suggestions=[{'title':'增加核对记录','reason':'保留导出后的核对结果','changes':[{'action':'add','id':'F03','fields':{'上级编号':'无','功能名称':'核对记录','说明':'保存核对数据和结果','验收标准':'核对结果可重新读取'}},{'action':'add','id':'F03-01','fields':{'上级编号':'F03','功能名称':'读取核对记录','说明':'读取最近一次核对记录','验收标准':'读取内容与上次保存一致','依赖':m['N3']}},{'action':'update','id':'F02','fields':{'依赖':'F03-01','验收标准':'文件可打开并包含全部订单记录'}}]}])
        self.assertFalse(s['adopted']);self.assertEqual(f.read()['plan']['revision'],base['plan']['revision'])
        p=f.call('preview_suggestions',revision=base['plan']['revision'],suggestion_id=s['id'],selected=['S01'])
        self.assertFalse(p['saved']);self.assertEqual(f.read()['plan']['revision'],base['plan']['revision'])
        f.commit(p);c=f.candidate();self.assertFalse(c['saved']);saved=f.save_candidate(c)
        self.assertEqual(saved['summary']['total'],4)
        r=f.progress(m['N3'],{'状态':'待审核','执行 Agent':'implementer-fixture','实现证据':'local fixture implementation'})
        self.assertEqual(r['summary']['review'],1);f.accept(m['N3'])
        reopened=f.progress(m['N3'],{'状态':'待审核'})
        self.assertEqual(reopened['summary']['review'],1);self.assertEqual(reopened['summary']['working'],0)
        self.assertFalse(f.items()[m['N3']]['checked'])
        self.assertTrue(f.call('history')['versions'])
        print('E2E',json.dumps({'mapping':m,'summary':reopened['summary']},ensure_ascii=False))
    def test_child_cancel_readopt_repeated_counts_and_preserves_acceptance_history(self):
        f=self.f
        p=f.edit(additions=[add('N1','F01','保存订单')]);f.commit(p);f.ledger();f.accept('F01-01')
        counts=[]
        for n in range(4):
            f.set_choices({'F01-01':False});counts.append(f.ledger()['summary']['total'])
            f.set_choices({'F01-01':True});counts.append(f.ledger()['summary']['total'])
            records=f.items();self.assertEqual([c['id'] for c in records['F01']['children']],['F01-01'])
            child=records['F01-01'];self.assertFalse(child['checked']);self.assertEqual(child['fields']['状态'],'进行中')
            self.assertEqual(child['fields']['实现证据'],'fixture local assertions')
            self.assertTrue(any(x.get('checked') for x in json.loads(child['fields']['规划同步历史'])))
        self.assertEqual(counts,[2]*8)
        self.assertLess(f.read()['ledger']['content'].index('F01-01 保存订单'),f.read()['ledger']['content'].index('F01 订单管理'))
        print('R3_CYCLES',counts)
    def test_multilevel_cancel_readopt_and_manual_parent_restore(self):
        f=self.f;m=self.tree();self.assertEqual(f.ledger()['summary']['total'],3)
        f.accept(m['N3']);f.progress(m['N2'],{'状态':'待审核','执行 Agent':'implementer-fixture','实现证据':'local parent fixture'})
        cancel=f.edit(selections=[{'id':m['N1'],'selected':False}]);f.commit(cancel)
        self.assertEqual(f.ledger()['summary']['total'],2)
        self.assert_rejected_unchanged(lambda:f.progress(m['N3'],{'状态':'待审核'}))
        restore=f.edit(selections=[{'id':m['N3'],'selected':True}]);f.commit(restore)
        self.assertEqual(f.ledger()['summary']['total'],3)
        self.assertFalse(f.items()[m['N3']]['checked'])
        f.progress(m['N1'],{'状态':'已取消'})
        self.assertEqual(summarize(parse(f.read()['ledger']['content']))['total'],2)
        self.assert_rejected_unchanged(lambda:f.progress(m['N3'],{'状态':'待审核'}))
        r=f.progress(m['N1'],{'状态':'待审核'});self.assertEqual(r['summary']['total'],3)
        self.assertEqual(f.items()[m['N1']]['fields']['状态'],'待审核')
    def test_all_explicit_noncomplete_states_revoke_review_preserve_exact_state(self):
        f=self.f;f.ledger()
        for status in ('未开始','进行中','待审核','受阻','已取消'):
            f.accept('F02');old=copy.deepcopy(f.items()['F02'])
            r=f.progress('F02',{'状态':status});item=f.items()['F02']
            self.assertEqual(item['fields']['状态'],status);self.assertFalse(item['checked'])
            self.assertEqual(item['fields']['审核 Agent'],'待审核')
            self.assertEqual(item['fields']['审核证据'],'待审核')
            snap=json.loads(item['fields']['进度更新历史'])[-1]['before'];self.assertTrue(snap['checked'])
            self.assertEqual(snap['fields']['审核 Agent'],old['fields']['审核 Agent'])
            self.assertEqual(snap['fields']['实现证据'],old['fields']['实现证据'])
            if status=='待审核':self.assertEqual((r['summary']['review'],r['summary']['working']),(1,0))
            if status=='已取消':self.assertEqual(r['summary']['total'],1)
            # Clear blocking status before fresh completion.
            f.progress('F02',{'状态':'进行中'})
        f.accept('F02');f.progress('F02',{'实现证据':'replacement fixture evidence'})
        self.assertEqual(f.items()['F02']['fields']['状态'],'进行中')
    def test_reversed_legacy_records_keep_parentage_fields_and_history(self):
        f=self.f;m=self.tree();text=f.read()['ledger']['content']
        parts=re.split(r'(?=^## 大功能 )',text,flags=re.M)
        revised=[parts[0]]
        for section in parts[1:]:
            header,body=section.split('\n',1)
            blocks=re.split(r'(?=^\s*- \[[ xX]\] F\d)',body,flags=re.M)
            actual=[b for b in blocks if re.match(r'^\s*- \[[ xX]\] F\d',b)]
            revised.append(header+'\n'+''.join(reversed(actual)))
        # External-editor fixture: same records and fields, reversed physical order.
        Path(f.p['ledger_path']).write_text(''.join(revised),encoding='utf-8')
        parsed=f.items();self.assertEqual([c['id'] for c in parsed[m['N1']]['children']],[m['N2']])
        self.assertEqual([c['id'] for c in parsed[m['N2']]['children']],[m['N3']])
        self.assertEqual(summarize(parse(f.read()['ledger']['content']))['total'],3)
        r=f.progress(m['N3'],{'状态':'待审核','执行 Agent':'legacy implementation','实现证据':'reversed record fixture'})
        self.assertEqual(r['summary']['review'],1);self.assertEqual(r['summary']['total'],3)
        f.ledger();self.assertEqual(f.items()[m['N3']]['fields']['实现证据'],'reversed record fixture')
    def test_original_r5_single_temporary_reference_roundtrip(self):
        f=self.f
        p=f.edit(additions=[add('N1','F01','备份订单')],updates=[{'id':'F02','fields':{'依赖':'N1'}}])
        expected=p['mapping']['N1']
        rows={r['编号']:r for r in editable_table(p['content'])['rows']}
        self.assertEqual(rows['F02']['依赖'],expected)
        f.commit(p);f.ledger()
        self.assertEqual(f.items()['F02']['fields']['依赖'],expected)
    def test_multiple_temporary_dependencies_forward_nested_and_known_final_id(self):
        f=self.f
        p=f.edit(additions=[add('N30','N10','深层检查','等待N20完成'),add('N20','F01','生成索引'),add('N10','F01','保存快照','N20')],updates=[{'id':'F02','fields':{'依赖':'等待N30完成，N10、N20；JSON1 和 F1-score 为说明'}}])
        rows={r['编号']:r for r in editable_table(p['content'])['rows']};m=p['mapping']
        self.assertEqual(rows['F02']['依赖'],f"等待{m['N30']}完成，{m['N10']}、{m['N20']}；JSON1 和 F1-score 为说明")
        self.assertEqual(rows[m['N30']]['依赖'],'等待'+m['N20']+'完成')
        f.commit(p);f.ledger();self.assertNotRegex(f.items()['F02']['fields']['依赖'],r'(?<![A-Za-z])N\d+')
        p=f.edit(additions=[add('N1','F01','未来编号功能')],updates=[{'id':'F02','fields':{'依赖':'F01-03'}}])
        self.assertEqual(p['mapping']['N1'],'F01-03');f.commit(p);f.ledger()
        self.assertEqual(f.items()['F02']['fields']['依赖'],'F01-03')
        print('R5_MAPPING',json.dumps(m,ensure_ascii=False))
    def test_invalid_dependencies_rejected_without_document_writes(self):
        f=self.f;f.ledger()
        for dependency in ('N99','等待N99完成','F99','等待F99完成','F01-99','【N99】'):
            for additions in ([],[add('N1','F01','新功能')]):
                self.assert_rejected_unchanged(lambda:f.edit(updates=[{'id':'F02','fields':{'依赖':dependency}}],additions=additions,preview=False))
        for dependency in ('N1','等待N1完成','F999'):
            rows=editable_table(BASE)['rows'];rows[-1]['依赖']=dependency
            self.assert_rejected_unchanged(lambda:f.save_plan(replace_features(BASE,rows)))
    def test_removal_and_addition_dependency_resolves_final_graph(self):
        f=self.f
        p=f.edit(additions=[add('N1','F01','旧索引')],updates=[{'id':'F02','fields':{'依赖':'N1'}}]);f.commit(p);f.ledger()
        p=f.edit(remove_ids=['F01-01'],additions=[add('N2','F01','新索引')],updates=[{'id':'F02','fields':{'依赖':'N2'}}]);self.assertEqual(p['mapping']['N2'],'F01-02')
        f.commit(p);f.ledger();items=f.items();self.assertEqual(items['F02']['fields']['依赖'],'F01-02')
        self.assertEqual(items['F01-01']['fields']['状态'],'已取消')
        self.assert_rejected_unchanged(lambda:f.edit(remove_ids=['F01-02'],preview=False))
    def test_stale_plan_suggestion_and_ledger_candidates_rejected(self):
        f=self.f;f.ledger();old=f.read();candidate=f.candidate()
        suggestion=f.call('record_suggestions',revision=old['plan']['revision'],analyst='review fixture',suggestions=[{'title':'补充导出说明','reason':'明确文件范围','changes':[{'action':'update','id':'F02','fields':{'说明':'导出当前全部本机订单'}}]}])
        p=f.edit(updates=[{'id':'F02','fields':{'备注':'用户确认本机范围'}}]);f.commit(p)
        self.assert_rejected_unchanged(lambda:f.call('preview_suggestions',revision=f.read()['plan']['revision'],suggestion_id=suggestion['id'],selected=['S01']))
        self.assert_rejected_unchanged(lambda:f.save_candidate(candidate))
        self.assert_rejected_unchanged(lambda:f.call('edit_features',revision=old['plan']['revision'],additions=[add('N1','F01','过期功能')]))
        c=f.candidate();f.progress('F02',{'状态':'待审核','执行 Agent':'fixture','实现证据':'fixture'})
        self.assert_rejected_unchanged(lambda:f.save_candidate(c))
    def test_completed_historical_evidence_cannot_be_edited_in_candidate(self):
        f=self.f;f.ledger();f.accept('F02')
        p=f.edit(updates=[{'id':'F02','fields':{'验收标准':'文件可打开且逐行对应全部订单'}}]);f.commit(p);f.ledger()
        item=f.items()['F02'];self.assertFalse(item['checked'])
        self.assertEqual(json.loads(item['fields']['规划同步历史'])[-1]['fields']['审核 Agent'],REVIEW['reviewer'])
        c=f.candidate()
        changed=c['content'].replace(REVIEW['reviewer'],'invented-reviewer')
        self.assertNotEqual(changed,c['content'])
        self.assert_rejected_unchanged(lambda:f.save_candidate(c,content=changed))
        self.assert_rejected_unchanged(lambda:f.save_candidate(c,content=c['content'].replace('fixture local assertions','rewritten implementation')))
    def test_completed_tree_structure_addition_still_refuses_history_rewrite(self):
        f=self.f;m=self.tree()
        for identity in (m['N3'],m['N2'],m['N1']):f.accept(identity)
        p=f.edit(additions=[add('N9',m['N2'],'新叶子')]);f.commit(p)
        self.assert_rejected_unchanged(lambda:f.candidate())
    def test_removed_historical_id_is_reserved_for_future_allocations(self):
        f=self.f;p=f.edit(additions=[add('N1','F01','旧保存')]);f.commit(p);f.ledger()
        p=f.edit(remove_ids=['F01-01']);f.commit(p);f.ledger()
        p=f.edit(additions=[add('N1','F01','新保存')]);self.assertEqual(p['mapping']['N1'],'F01-02')
        f.commit(p);f.ledger();self.assertEqual(f.items()['F01-01']['fields']['状态'],'已取消')
if __name__=='__main__':unittest.main(verbosity=2)
