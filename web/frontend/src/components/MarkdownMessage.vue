<template>
  <div class="markdown-message" v-html="renderedHtml"></div>
</template>

<script setup lang="ts">
import DOMPurify from "dompurify";
import MarkdownIt from "markdown-it";
import { computed } from "vue";

const props = defineProps<{
  content: string;
}>();

const markdown = new MarkdownIt({
  html: false,
  breaks: true,
  linkify: true,
});

const defaultLinkOpen = markdown.renderer.rules.link_open;

markdown.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  const token = tokens[idx];
  const href = token.attrGet("href") || "";
  if (href && !isSafeHref(href)) {
    token.attrSet("href", "#");
  }
  token.attrSet("target", "_blank");
  token.attrSet("rel", "noopener noreferrer");
  return defaultLinkOpen ? defaultLinkOpen(tokens, idx, options, env, self) : self.renderToken(tokens, idx, options);
};

const renderedHtml = computed(() =>
  DOMPurify.sanitize(markdown.render(props.content || ""), {
    ADD_ATTR: ["target", "rel"],
    FORBID_TAGS: ["script", "style", "iframe", "object", "embed"],
  }),
);

function isSafeHref(href: string): boolean {
  return /^(https?:|mailto:|#|\/)/i.test(href);
}
</script>
