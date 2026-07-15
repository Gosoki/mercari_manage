<template>
  <div>
    <el-card shadow="never" class="search-card">
      <el-row :gutter="12" align="middle">
        <el-col :xs="24" :md="16" class="search-left-group">
          <el-date-picker
            v-model="dateRange"
            type="daterange"
            :range-separator="t('common.to')"
            :start-placeholder="t('common.startDate')"
            :end-placeholder="t('common.endDate')"
            value-format="x"
          />
        </el-col>
        <el-col :xs="24" :md="8" class="search-actions">
          <el-button type="primary" :loading="loading" @click="load">{{ t('system.settlementQuery') }}</el-button>
        </el-col>
      </el-row>
    </el-card>

    <el-card shadow="never" class="summary-card" v-if="loaded">
      <div class="summary-grid">
        <div class="summary-item">
          <div class="summary-label">{{ t('system.settlementOverallNet') }}</div>
          <div class="summary-value">¥{{ formatYen(overall.net_income) }}</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">{{ t('system.settlementAssignedNet') }}</div>
          <div class="summary-value">¥{{ formatYen(assignedNet) }}</div>
        </div>
        <div class="summary-item" v-if="unassignedNet !== 0">
          <div class="summary-label">{{ t('system.settlementUnassignedNet') }}</div>
          <div class="summary-value warn">¥{{ formatYen(unassignedNet) }}</div>
        </div>
        <div class="summary-item consumable-item">
          <div class="summary-label">{{ t('system.settlementRate') }}</div>
          <div class="rate-input-wrap">
            <span class="rate-prefix">{{ t('system.settlementRateCny') }}</span>
            <el-input-number
              v-model="exchangeRate"
              :min="0"
              :precision="4"
              :step="0.1"
              :controls="false"
              class="rate-input"
            />
            <span class="rate-suffix">{{ t('system.settlementRateJpyUnit') }}</span>
          </div>
        </div>
        <div class="summary-item">
          <div class="summary-label">{{ t('system.settlementTotalFinal') }}</div>
          <div class="summary-value strong">¥{{ formatYen(totals.final_amount) }}</div>
          <div class="summary-sub" v-if="hasRate">≈ ￥{{ formatCny(totals.final_amount_cny) }} {{ t('system.settlementCnyUnit') }}</div>
        </div>
      </div>
      <div class="summary-hint" v-if="unassignedNet !== 0">{{ t('system.settlementUnassignedHint') }}</div>
    </el-card>

    <el-card shadow="never" class="cost-card" v-if="loaded">
      <div class="cost-head">
        <span class="cost-title">{{ t('system.settlementConsumableTable') }}</span>
        <span class="cost-tip">{{ t('system.settlementConsumableTableTip') }}</span>
        <el-button size="small" @click="addConsumable">{{ t('system.settlementRowAdd') }}</el-button>
      </div>
      <el-table :data="consumables" size="small">
        <el-table-column :label="t('system.settlementConsumableName')" min-width="160">
          <template #default="{ row }">
            <span v-if="row.fixed" class="fixed-name">{{ displayName(row) }}</span>
            <el-input v-else v-model="row.name" size="small" :placeholder="t('system.settlementConsumableNamePh')" />
          </template>
        </el-table-column>
        <el-table-column :label="t('common.quantity')" width="130">
          <template #default="{ row }">
            <el-input-number v-model="row.quantity" :min="0" :precision="0" :controls="false" size="small" style="width: 100%" />
          </template>
        </el-table-column>
        <el-table-column :label="t('system.settlementUnitPrice')" width="140">
          <template #default="{ row }">
            <el-input-number v-model="row.unit_price" :min="0" :precision="2" :controls="false" size="small" style="width: 100%" />
          </template>
        </el-table-column>
        <el-table-column :label="t('system.settlementCurrency')" width="120">
          <template #default="{ row }">
            <el-select v-model="row.currency" size="small" style="width: 100%">
              <el-option :label="t('system.settlementRateJpyUnit')" value="JPY" />
              <el-option :label="t('system.settlementCnyUnit')" value="CNY" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column :label="t('system.settlementSubtotal')" min-width="150" align="right">
          <template #default="{ row }">{{ rowSubtotalText(row) }}</template>
        </el-table-column>
        <el-table-column :label="t('common.actions')" width="70" align="center">
          <template #default="{ row, $index }">
            <el-button v-if="!row.fixed" size="small" type="danger" link @click="removeConsumable($index)">{{ t('common.delete') }}</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="cost-foot">
        <span>{{ t('system.settlementConsumableTotalLabel') }}</span>
        <strong>¥{{ formatYen(consumableTotalJpy) }}</strong>
      </div>
    </el-card>

    <el-card shadow="never" class="cost-card" v-if="loaded">
      <div class="cost-head">
        <span class="cost-title">{{ t('system.settlementEquipmentTable') }}</span>
        <span class="cost-tip">{{ t('system.settlementEquipmentTableTip') }}</span>
        <el-button size="small" @click="addEquipment">{{ t('system.settlementRowAdd') }}</el-button>
      </div>
      <el-table :data="equipments" size="small">
        <el-table-column :label="t('system.settlementEquipmentName')" min-width="160">
          <template #default="{ row }">
            <el-input v-model="row.name" size="small" :placeholder="t('system.settlementEquipmentNamePh')" />
          </template>
        </el-table-column>
        <el-table-column :label="t('common.quantity')" width="130">
          <template #default="{ row }">
            <el-input-number v-model="row.quantity" :min="0" :precision="0" :controls="false" size="small" style="width: 100%" />
          </template>
        </el-table-column>
        <el-table-column :label="t('system.settlementUnitPrice')" width="140">
          <template #default="{ row }">
            <el-input-number v-model="row.unit_price" :min="0" :precision="2" :controls="false" size="small" style="width: 100%" />
          </template>
        </el-table-column>
        <el-table-column :label="t('system.settlementCurrency')" width="120">
          <template #default="{ row }">
            <el-select v-model="row.currency" size="small" style="width: 100%">
              <el-option :label="t('system.settlementRateJpyUnit')" value="JPY" />
              <el-option :label="t('system.settlementCnyUnit')" value="CNY" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column :label="t('system.settlementSubtotal')" min-width="150" align="right">
          <template #default="{ row }">{{ rowSubtotalText(row) }}</template>
        </el-table-column>
        <el-table-column :label="t('common.actions')" width="70" align="center">
          <template #default="{ $index }">
            <el-button size="small" type="danger" link @click="removeEquipment($index)">{{ t('common.delete') }}</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="cost-foot" v-if="!equipments.length">
        <span class="cost-empty">{{ t('system.settlementEquipmentEmpty') }}</span>
      </div>
      <div class="cost-foot" v-else>
        <span>{{ t('system.settlementEquipmentTotalLabel') }}</span>
        <strong>¥{{ formatYen(equipmentTotalJpy) }}</strong>
      </div>
    </el-card>

    <div v-loading="loading" class="settlement-cards">
      <el-card
        v-for="row in tableRows"
        :key="row.owner_user_id"
        shadow="hover"
        class="owner-card"
      >
        <div class="owner-card-head">
          <span class="owner-name">{{ row.owner_name }}</span>
          <span class="owner-orders">{{ row.order_count }} {{ t('system.settlementOrdersUnit') }}</span>
        </div>
        <div class="owner-card-body">
          <div class="stat-line">
            <span class="stat-label">{{ t('system.settlementAmount') }}</span>
            <span class="stat-val">¥{{ formatYen(row.sum_amount) }}</span>
          </div>
          <div class="stat-line">
            <span class="stat-label">{{ t('system.settlementServiceFee') }}</span>
            <span class="stat-val minus">-¥{{ formatYen(row.sum_service_fee) }}</span>
          </div>
          <div class="stat-line">
            <span class="stat-label">{{ t('system.settlementShippingFee') }}</span>
            <span class="stat-val minus">-¥{{ formatYen(row.sum_shipping_fee) }}</span>
          </div>
          <div class="stat-line">
            <span class="stat-label">{{ t('system.settlementPackaging') }}</span>
            <span class="stat-val minus">-¥{{ formatYen(row.packaging) }}</span>
          </div>
          <div class="stat-line net-line">
            <span class="stat-label">{{ t('system.settlementNetIncome') }}</span>
            <span class="stat-val" :class="{ warn: Number(row.net_income) < 0 }">¥{{ formatYen(row.net_income) }}</span>
          </div>
          <div class="stat-line">
            <span class="stat-label">{{ t('system.settlementConsumableShare') }}</span>
            <span class="stat-val minus">-¥{{ formatYen(row.consumable_share) }}</span>
          </div>
          <div class="stat-line ratio-line">
            <span class="stat-label">{{ t('system.settlementEquipmentRatio') }}</span>
            <el-input-number
              v-model="ratioMap[row.owner_user_id]"
              :min="0"
              :precision="2"
              :controls="false"
              size="small"
              class="ratio-input"
            />
          </div>
          <div class="stat-line">
            <span class="stat-label">{{ t('system.settlementEquipmentShare') }}</span>
            <span class="stat-val minus">-¥{{ formatYen(row.equipment_share) }}</span>
          </div>
        </div>
        <div class="owner-card-foot">
          <span class="foot-label">{{ t('system.settlementFinalAmount') }}</span>
          <div class="foot-amounts">
            <span class="foot-val" :class="{ warn: Number(row.final_amount) < 0 }">¥{{ formatYen(row.final_amount) }}</span>
            <span class="foot-val-cny" v-if="hasRate" :class="{ warn: Number(row.final_amount_cny) < 0 }">
              ≈ ￥{{ formatCny(row.final_amount_cny) }} {{ t('system.settlementCnyUnit') }}
            </span>
          </div>
        </div>
      </el-card>

      <el-empty
        v-if="loaded && !tableRows.length"
        class="cards-empty"
        :description="t('system.settlementNoData')"
      />
    </div>
  </div>
</template>

<script src="./script.js"></script>
<style scoped src="./style.css"></style>
