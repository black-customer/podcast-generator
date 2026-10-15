/* 保留同一步的原生控件与媒体节点，避免保存和帮助操作打断输入。 */
"use strict";
const UIContinuity = (() => {
  const key = node => node.nodeType === 1
    ? node.id || node.getAttribute('data-ui-key') || node.getAttribute('data-train') || '' : '';
  function compatible(a, b) {
    return a && a.nodeType === b.nodeType && a.nodeName === b.nodeName && key(a) === key(b);
  }
  function patch(target, source) {
    if (target.nodeType === 3) {
      if (target.nodeValue !== source.nodeValue) target.nodeValue = source.nodeValue;
      return;
    }
    if(target.hasAttribute('data-ui-preserve'))return;
    const liveControl = target.matches('input,textarea,select');
    for (const attr of [...target.attributes]) {
      if (!source.hasAttribute(attr.name) && !(attr.name === 'open' && target.tagName === 'DETAILS'))
        target.removeAttribute(attr.name);
    }
    for (const attr of [...source.attributes]) {
      if (liveControl && ['value','checked','selected'].includes(attr.name)) continue;
      if (target.getAttribute(attr.name) !== attr.value) target.setAttribute(attr.name, attr.value);
    }
    if (liveControl || target.matches('audio,video')) return;
    let cursor = target.firstChild;
    for (const child of [...source.childNodes]) {
      let match = compatible(cursor, child) ? cursor : null;
      if (!match && key(child)) match = [...target.childNodes].find(n => compatible(n, child));
      if (match) {
        if (match !== cursor) target.insertBefore(match, cursor);
        patch(match, child);
        cursor = match.nextSibling;
      } else target.insertBefore(child.cloneNode(true), cursor);
    }
    while (cursor) { const next = cursor.nextSibling; cursor.remove(); cursor = next; }
  }
  function update(target, html, preserve) {
    const scrolls = [target, target.closest('.main-content'), document.scrollingElement]
      .filter(Boolean).map(el => [el, el.scrollTop]);
    if (preserve) {
      const template = target.cloneNode(false); template.innerHTML = html;
      patch(target, template);
      scrolls.forEach(([el, top]) => { el.scrollTop = top; });
    } else {
      target.innerHTML = html;
      scrolls.forEach(([el]) => { el.scrollTop = 0; });
    }
  }
  let current = '', positions = new Map();
  function navigation(hash) {
    const scroller = document.querySelector('.main-content');
    if (current.startsWith('#/bank') || current.startsWith('#/practice')) {
      positions.set(current, scroller?.scrollTop || 0);
      sessionStorage.setItem('experience-bank-route', current);
    }
    current = hash;
  }
  function restoreBank() {
    const top = positions.get(location.hash);
    if (top !== undefined) {
      document.querySelector('.main-content')?.scrollTo(0, top);
    }
  }
  const bankLink = () => sessionStorage.getItem('experience-bank-route') || '#/bank';
  let accepted=false;
  function allowNavigation(hash) {
    const recording=typeof TrainingUI!=='undefined' && TrainingUI.recording();
    const baseline=typeof TrainingBaseline!=='undefined' && TrainingBaseline.recording();
    if(accepted || !current || hash===current || !(recording || baseline)){accepted=false;return true;}
    history.replaceState(null,'',current);
    if(document.getElementById('recording-leave-dialog'))return false;
    const dialog=document.createElement('dialog');dialog.id='recording-leave-dialog';dialog.className='product-dialog';
    dialog.innerHTML='<h2>先保存这次录音</h2><p>录音正在进行或保存中。停止并保存后，再离开练习。</p><div class="study-actions"><button type="button" class="study-button" data-stay>继续留在这里</button><button type="button" class="study-button primary" data-leave>停止并保存后离开</button></div><p role="status"></p>';
    document.body.append(dialog);dialog.showModal();
    dialog.querySelector('[data-stay]').onclick=()=>dialog.close();
    dialog.addEventListener('close',()=>dialog.remove());
    dialog.querySelector('[data-leave]').onclick=async event=>{
      const button=event.currentTarget;button.disabled=true;
      try{
        const saved=recording?await TrainingUI.finishRecording():await TrainingBaseline.finishRecording();
        if(saved){dialog.close();accepted=true;location.hash=hash;}
        else dialog.querySelector('[role=status]').textContent='保存尚未成功。录音仍保留，请留在本页重试。';
      }catch(e){dialog.querySelector('[role=status]').textContent=e.message;}
      finally{button.disabled=false;}
    };
    return false;
  }
  window.addEventListener('beforeunload',event=>{
    if((typeof TrainingUI!=='undefined' && TrainingUI.recording()) || (typeof TrainingBaseline!=='undefined' && TrainingBaseline.recording())){event.preventDefault();event.returnValue='';}
  });
  document.addEventListener('click', event => {
    const link=event.target.closest('a[href="#/bank"],a[href="#/practice"]');
    if(link && !event.ctrlKey && !event.metaKey && !event.shiftKey && bankLink().includes('?')) {
      event.preventDefault(); location.hash=bankLink();
    }
  });
  return {update, navigation, restoreBank, bankLink, allowNavigation};
})();
