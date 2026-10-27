class CreateCallbackDeliveries < ActiveRecord::Migration[5.2]
  def change
    create_table :callback_deliveries do |t|
      t.references :submission, null: false, index: { unique: true }, foreign_key: true
      t.text :url, null: false
      t.text :payload, null: false
      t.integer :attempts, null: false, default: 0
      t.datetime :next_attempt_at, null: false, precision: 6
      t.datetime :delivered_at, precision: 6
      t.datetime :exhausted_at, precision: 6
      t.integer :last_status
      t.timestamps precision: 6
    end
    add_index :callback_deliveries, :next_attempt_at,
              where: "delivered_at IS NULL AND exhausted_at IS NULL", name: "callback_deliveries_due"
  end
end
