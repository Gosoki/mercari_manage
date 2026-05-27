<template>
  <div class="dashboard">
    <!-- 库存管理统计 -->
    <el-card class="section-card inventory-stats-wrap" shadow="never">
      <template #header>
        <div class="card-header">
          <el-icon color="#409EFF"><Goods /></el-icon>
          <span>{{ t('dashboard.inventoryMgmt') }}</span>
        </div>
      </template>
      <el-row :gutter="16" class="stat-row inventory-stat-row">
        <el-col :xs="12" :sm="12" :md="8" :lg="4" v-for="card in statCards" :key="card.key">
          <div class="stat-card" :style="{ borderTopColor: card.color }">
            <div class="stat-icon" :style="{ background: card.color + '20', color: card.color }">
              <el-icon size="22"><component :is="card.icon" /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ summary[card.key] ?? '-' }}</div>
              <div class="stat-label">{{ t(card.labelKey) }}</div>
            </div>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <!-- 订单汇总：近 30 天本地自然日（Unix 秒区间），与订单页 /orders/stats 口径一致（COALESCE 最后更新/购入/下单） -->
    <el-card class="section-card order-stats-wrap" shadow="never" v-loading="orderStatsLoading">
      <template #header>
        <div class="card-header">
          <el-icon color="#67C23A"><Tickets /></el-icon>
          <span>{{ t('dashboard.orderStats') }}</span>
        </div>
      </template>
      <el-row :gutter="16" class="stat-row order-stat-row">
        <el-col :xs="12" :sm="12" :md="8" :lg="4" v-for="card in orderStatCards" :key="card.label">
          <div
            class="stat-card order-stat-card"
            :class="card.cardClass"
            :style="{ borderTopColor: card.color }"
          >
            <div class="stat-icon" :style="{ background: card.color + '20', color: card.color }">
              <el-icon size="22"><component :is="card.icon" /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value-row">
                <span class="stat-value" :class="card.valueClass">{{ card.display }}</span>
                <span class="stat-today">({{ t('dashboard.todayNew', { count: card.todayDisplay }) }})</span>
              </div>
              <div class="stat-label">{{ card.label }}</div>
            </div>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <!-- 最近交易 -->
    <el-card class="section-card" shadow="never">
      <template #header>
        <div class="card-header">
          <el-icon color="#409EFF"><List /></el-icon>
          <span>{{ t('dashboard.recentTx') }}</span>
        </div>
      </template>
      <el-table :data="recentTx" size="small" stripe>
        <el-table-column :label="t('dashboard.txTime')" width="160">
          <template #default="{ row }">{{ formatUnixSecLocal(row.created_at) }}</template>
        </el-table-column>
        <el-table-column :label="t('dashboard.txType')" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.type === 'in' ? 'success' : row.type === 'out' ? 'danger' : 'warning'" size="small">
              {{ txTypeLabel(row.type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('dashboard.txInventory')" prop="inventory_name" />
        <el-table-column :label="t('dashboard.txWarehouse')" prop="warehouse_name" />
        <el-table-column :label="t('dashboard.txQuantity')" prop="quantity" width="80" align="center" />
        <el-table-column :label="t('dashboard.txOperator')" prop="operator" width="90" />
      </el-table>
    </el-card>
  </div>
</template>

<script src="./script.js"></script>
<style scoped src="./style.css"></style>
