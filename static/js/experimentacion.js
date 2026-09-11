/* Editor progresivo: el formulario y los cálculos también funcionan sin JS. */
(() => {
  const inputs = document.querySelectorAll('#formula-form textarea');
  let input = inputs[0];
  const result = document.getElementById('resultado-libre');
  function invalidate() { result.replaceChildren(); }
  inputs.forEach(field => {
    field.addEventListener('input', invalidate);
    field.addEventListener('focus', () => { input = field; });
  });
  document.querySelectorAll('[data-insert], [data-wrap]').forEach(button => {
    button.addEventListener('click', () => {
      let start = input.selectionStart;
      let end = input.selectionEnd;
      let text = button.dataset.insert;
      if (button.dataset.wrap) {
        if (start === end) {
          if (input.id === 'id_premisas') {
            start = input.value.lastIndexOf('\n', start - 1) + 1;
            end = input.value.indexOf('\n', end);
            if (end === -1) end = input.value.length;
          } else { start = 0; end = input.value.length; }
        }
        text = `${button.dataset.wrap === 'negate' ? '~' : ''}(${input.value.slice(start, end)})`;
      }
      if (input.value.length - (end - start) + text.length > input.maxLength) return;
      input.setRangeText(text, start, end, 'end');
      input.focus();
      invalidate();
    });
  });
})();
