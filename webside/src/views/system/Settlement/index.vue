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
            :disabled-date="disabledDate"
            value-format="x"
          />
        </el-col>
        <el-col :xs="24" :md="8" class="search-actions">
          <el-button type="primary" :loading="loading" @click="load">{{ t('system.settlementQuery') }}</el-button>
          <el-button type="success" :loading="saving" :disabled="!loaded || !tableRows.length" @click="saveSettlement">{{ t('system.settlementSave') }}</el-button>
        </el-col>
      </el-row>
    </el-card>

    <el-card shadow="never" class="summary-card" v-if="loaded">
      <div class="summary-grid">
        <div class="summary-item">
          <div class="summary-label">{{ t('system.settlementOverallNet') }}</div>
          <div class="summary-value">JP¥{{ formatYen(overall.net_income) }}</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">{{ t('system.settlementAssignedNet') }}</div>
          <div class="summary-value">JP¥{{ formatYen(assignedNet) }}</div>
        </div>
        <div class="summary-item" v-if="unassignedNet !== 0">
          <div class="summary-label">{{ t('system.settlementUnassignedNet') }}</div>
          <div class="summary-value warn">JP¥{{ formatYen(unassignedNet) }}</div>
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
          <div class="summary-value strong">JP¥{{ formatYen(totals.final_amount) }}</div>
          <div class="summary-sub" v-if="hasRate">≈ CN¥{{ formatCny(totals.final_amount_cny) }}</div>
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
            <el-input-number v-model="row.unit_price" :min="0" :precision="row.currency === 'CNY' ? 2 : 0" :controls="false" size="small" style="width: 100%" />
          </template>
        </el-table-column>
        <el-table-column :label="t('system.settlementCurrency')" width="150">
          <template #default="{ row }">
            <el-select v-model="row.currency" size="small" class="currency-select" style="width: 100%" @change="onCurrencyChange(row)">
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
        <strong>JP¥{{ formatYen(consumableTotalJpy) }}</strong>
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
            <el-input-number v-model="row.unit_price" :min="0" :precision="row.currency === 'CNY' ? 2 : 0" :controls="false" size="small" style="width: 100%" />
          </template>
        </el-table-column>
        <el-table-column :label="t('system.settlementCurrency')" width="150">
          <template #default="{ row }">
            <el-select v-model="row.currency" size="small" class="currency-select" style="width: 100%" @change="onCurrencyChange(row)">
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
        <template #empty>{{ t('system.settlementEquipmentEmpty') }}</template>
      </el-table>
      <div class="cost-foot" v-if="equipments.length">
        <span>{{ t('system.settlementEquipmentTotalLabel') }}</span>
        <strong>JP¥{{ formatYen(equipmentTotalJpy) }}</strong>
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
            <span class="stat-val">JP¥{{ formatYen(row.sum_amount) }}</span>
          </div>
          <div class="stat-line">
            <span class="stat-label">{{ t('system.settlementServiceFee') }}</span>
            <span class="stat-val minus">-JP¥{{ formatYen(row.sum_service_fee) }}</span>
          </div>
          <div class="stat-line">
            <span class="stat-label">{{ t('system.settlementShippingFee') }}</span>
            <span class="stat-val minus">-JP¥{{ formatYen(row.sum_shipping_fee) }}</span>
          </div>
          <div class="stat-line">
            <span class="stat-label">{{ t('system.settlementPackaging') }}</span>
            <span class="stat-val minus">-JP¥{{ formatYen(row.packaging) }}</span>
          </div>
          <div class="stat-line net-line">
            <span class="stat-label">{{ t('system.settlementNetIncome') }}</span>
            <span class="stat-val" :class="{ warn: Number(row.net_income) < 0 }">JP¥{{ formatYen(row.net_income) }}</span>
          </div>
          <div class="stat-line">
            <span class="stat-label">{{ t('system.settlementConsumableShare') }}</span>
            <span class="stat-val minus">-JP¥{{ formatYen(row.consumable_share) }}</span>
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
            <span class="stat-val minus">-JP¥{{ formatYen(row.equipment_share) }}</span>
          </div>
        </div>
        <div class="owner-card-foot">
          <span class="foot-label">{{ t('system.settlementFinalAmount') }}</span>
          <div class="foot-amounts">
            <span class="foot-val" :class="{ warn: Number(row.final_amount) < 0 }">JP¥{{ formatYen(row.final_amount) }}</span>
            <span class="foot-val-cny" v-if="hasRate" :class="{ warn: Number(row.final_amount_cny) < 0 }">
              ≈ CN¥{{ formatCny(row.final_amount_cny) }}
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

    <el-card shadow="never" class="records-card" v-if="records.length">
      <div class="cost-head">
        <span class="cost-title">{{ t('system.settlementRecords') }}</span>
      </div>
      <el-table :data="records" size="small" stripe>
        <el-table-column :label="t('system.settlementRecordPeriod')" min-width="200">
          <template #default="{ row }">{{ formatDate(row.start_date) }} ~ {{ formatDate(row.end_date) }}</template>
        </el-table-column>
        <el-table-column :label="t('system.settlementNetIncome')" width="130" align="right">
          <template #default="{ row }">JP¥{{ formatYen(row.overall_net_income) }}</template>
        </el-table-column>
        <el-table-column :label="t('system.settlementTotalFinal')" width="130" align="right">
          <template #default="{ row }">JP¥{{ formatYen(row.final_total) }}</template>
        </el-table-column>
        <el-table-column :label="t('system.settlementRecordOperator')" width="120">
          <template #default="{ row }">{{ row.operator || '-' }}</template>
        </el-table-column>
        <el-table-column :label="t('system.settlementRecordTime')" width="180">
          <template #default="{ row }">{{ row.created_at || '-' }}</template>
        </el-table-column>
        <el-table-column :label="t('common.actions')" width="90" align="center">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="openDetail(row)">{{ t('system.settlementDetail') }}</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog
      v-model="detailVisible"
      :title="t('system.settlementDetailTitle')"
      width="90%"
      top="5vh"
      class="settlement-detail-dialog"
    >
      <template v-if="detailRecord">
        <el-descriptions :column="4" border size="small" class="detail-desc">
          <el-descriptions-item :label="t('system.settlementRecordPeriod')" :span="2">
            {{ formatDate(detailRecord.start_date) }} ~ {{ formatDate(detailRecord.end_date) }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.settlementRate')">
            <span v-if="detailRecord.exchange_rate">1 : {{ detailRecord.exchange_rate }}</span>
            <span v-else>-</span>
          </el-descriptions-item>
          <el-descriptions-item :label="t('system.settlementRecordOperator')">{{ detailRecord.operator || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('system.settlementOverallNet')">JP¥{{ formatYen(detailRecord.overall_net_income) }}</el-descriptions-item>
          <el-descriptions-item :label="t('system.settlementPackaging')">JP¥{{ formatYen(detailRecord.overall_packaging) }}</el-descriptions-item>
          <el-descriptions-item :label="t('system.settlementConsumableTotalLabel')">JP¥{{ formatYen(detailRecord.consumable_total) }}</el-descriptions-item>
          <el-descriptions-item :label="t('system.settlementEquipmentTotalLabel')">JP¥{{ formatYen(detailRecord.equipment_total) }}</el-descriptions-item>
          <el-descriptions-item :label="t('system.settlementTotalFinal')" :span="4">
            <strong style="color: var(--el-color-primary)">JP¥{{ formatYen(detailRecord.final_total) }}</strong>
          </el-descriptions-item>
        </el-descriptions>

        <div class="detail-section-title">{{ t('system.settlementDetailOwners') }}</div>
        <el-table :data="detailRecord.rows || []" size="small" stripe border>
          <el-table-column :label="t('system.settlementOwner')" prop="owner_name" min-width="90" />
          <el-table-column :label="t('system.settlementOrderCount')" prop="order_count" min-width="60" align="center" />
          <el-table-column :label="t('system.settlementAmount')" min-width="90" align="right">
            <template #default="{ row }">JP¥{{ formatYen(row.sum_amount) }}</template>
          </el-table-column>
          <el-table-column :label="t('system.settlementServiceFee')" min-width="80" align="right">
            <template #default="{ row }">-JP¥{{ formatYen(row.sum_service_fee) }}</template>
          </el-table-column>
          <el-table-column :label="t('system.settlementShippingFee')" min-width="80" align="right">
            <template #default="{ row }">-JP¥{{ formatYen(row.sum_shipping_fee) }}</template>
          </el-table-column>
          <el-table-column :label="t('system.settlementPackaging')" min-width="80" align="right">
            <template #default="{ row }">-JP¥{{ formatYen(row.packaging) }}</template>
          </el-table-column>
          <el-table-column :label="t('system.settlementNetIncome')" min-width="90" align="right">
            <template #default="{ row }">JP¥{{ formatYen(row.net_income) }}</template>
          </el-table-column>
          <el-table-column :label="t('system.settlementConsumableShare')" min-width="80" align="right">
            <template #default="{ row }">-JP¥{{ formatYen(row.consumable_share) }}</template>
          </el-table-column>
          <el-table-column :label="t('system.settlementEquipmentRatio')" min-width="70" align="center">
            <template #default="{ row }">{{ row.equipment_ratio ?? '-' }}</template>
          </el-table-column>
          <el-table-column :label="t('system.settlementEquipmentShare')" min-width="80" align="right">
            <template #default="{ row }">-JP¥{{ formatYen(row.equipment_share) }}</template>
          </el-table-column>
          <el-table-column :label="t('system.settlementCnyUnit')" min-width="95" align="right">
            <template #default="{ row }">
              <span v-if="row.final_amount_cny != null">CN¥{{ formatCny(row.final_amount_cny) }}</span>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column :label="t('system.settlementFinalAmount')" min-width="100" align="right">
            <template #default="{ row }"><strong>JP¥{{ formatYen(row.final_amount) }}</strong></template>
          </el-table-column>
        </el-table>

        <div class="detail-two-col">
          <div class="detail-col">
            <div class="detail-section-title">{{ t('system.settlementConsumableTable') }}</div>
            <el-table :data="detailRecord.consumables || []" size="small" border>
              <el-table-column :label="t('system.settlementConsumableName')" min-width="120">
                <template #default="{ row }">{{ displayName(row) }}</template>
              </el-table-column>
              <el-table-column :label="t('common.quantity')" prop="quantity" width="80" align="right" />
              <el-table-column :label="t('system.settlementUnitPrice')" prop="unit_price" width="90" align="right" />
              <el-table-column :label="t('system.settlementCurrency')" width="90">
                <template #default="{ row }">{{ currencyLabel(row.currency) }}</template>
              </el-table-column>
            </el-table>
          </div>
          <div class="detail-col">
            <div class="detail-section-title">{{ t('system.settlementEquipmentTable') }}</div>
            <el-table :data="detailRecord.equipments || []" size="small" border>
              <el-table-column :label="t('system.settlementEquipmentName')" min-width="120">
                <template #default="{ row }">{{ row.name || '-' }}</template>
              </el-table-column>
              <el-table-column :label="t('common.quantity')" prop="quantity" width="80" align="right" />
              <el-table-column :label="t('system.settlementUnitPrice')" prop="unit_price" width="90" align="right" />
              <el-table-column :label="t('system.settlementCurrency')" width="90">
                <template #default="{ row }">{{ currencyLabel(row.currency) }}</template>
              </el-table-column>
              <template #empty>{{ t('system.settlementEquipmentEmpty') }}</template>
            </el-table>
          </div>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script src="./script.js"></script>
<style scoped src="./style.css"></style>
