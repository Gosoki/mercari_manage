<template>
  <ul class="ct" :class="{ root }">
    <li v-for="(n, i) in nodes" :key="i">
      <div class="ct-node">
        <span v-if="n.tag" class="ct-tag">{{ n.tag }}</span>
        <span class="ct-fn">{{ n.fn }}</span>
        <span v-if="n.loc" class="ct-loc">{{ n.loc }}</span>
        <span v-for="(io, j) in n.io || []" :key="j" class="ct-io" :class="io.t">{{ io.x }}</span>
        <span v-if="n.note" class="ct-note">{{ n.note }}</span>
      </div>
      <CallTree v-if="n.children && n.children.length" :nodes="n.children" />
    </li>
  </ul>
</template>

<script>
// 递归调用链树:节点 { tag?, fn, loc?, note?, io?: [{t:'r'|'w'|'api'|'ext', x}], children? }
export default {
  name: 'CallTree',
  props: {
    nodes: { type: Array, required: true },
    root: { type: Boolean, default: false }
  }
}
</script>

<style scoped>
.ct { list-style: none; margin: 0; padding: 0 0 0 22px; }
.ct.root { padding-left: 0; }
.ct li { position: relative; padding: 3px 0 3px 18px; }
.ct li::before {
  content: ""; position: absolute; left: 0; top: 0; height: 100%;
  border-left: 1.5px solid var(--border);
}
.ct li:last-child::before { height: 17px; }
.ct li::after {
  content: ""; position: absolute; left: 0; top: 17px; width: 13px;
  border-top: 1.5px solid var(--border);
}
.ct.root > li { padding-left: 0; }
.ct.root > li::before, .ct.root > li::after { display: none; }

.ct-node { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 8px; line-height: 1.5; }
.ct-fn { font-family: var(--mono); font-size: 13px; font-weight: 600; color: var(--ink); }
.ct-loc { font-family: var(--mono); font-size: 11px; color: var(--faint); }
.ct-note { font-size: 12px; color: var(--muted); }
.ct-tag {
  font-family: var(--mono); font-size: 10.5px; font-weight: 700;
  color: var(--proc-ink); background: var(--proc-fill);
  border: 1px solid var(--proc-stroke); border-radius: 3px; padding: 0 6px;
}
.ct-io {
  font-family: var(--mono); font-size: 10.5px;
  border: 1px solid; border-radius: 3px; padding: 0 6px; white-space: nowrap;
}
.ct-io.r { color: var(--store-ink); border-color: var(--store-stroke); }
.ct-io.w { color: #f0a35c; border-color: #a06a30; }
.ct-io.api { color: var(--proc-ink); border-color: var(--proc-stroke); }
.ct-io.ext { color: var(--muted); border-color: var(--border); }
</style>
