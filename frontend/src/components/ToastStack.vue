<script setup lang="ts">
import { toasts } from '../ui/toast'
</script>

<template>
  <div class="toasts" aria-live="polite" aria-atomic="false">
    <div v-for="item in toasts" :key="item.id" class="toast" :class="item.kind">{{ item.message }}</div>
  </div>
</template>
