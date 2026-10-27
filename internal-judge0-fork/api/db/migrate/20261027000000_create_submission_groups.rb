class CreateSubmissionGroups < ActiveRecord::Migration[5.2]
  def change
    create_table :submission_groups do |t|
      t.string :token, null: false
      t.string :idempotency_key, null: false
      t.string :payload_sha256, null: false
      t.string :state, null: false, default: "queued"
      t.string :execution_model, null: false, default: "fresh"
      t.text :shared_script
      t.string :shared_attempt_token
      t.datetime :shared_started_at, precision: 6
      t.datetime :shared_finished_at, precision: 6
      t.string :shared_termination
      t.string :shared_execution_host
      t.integer :shared_worker_pid
      t.bigint :shared_worker_started_ticks
      t.datetime :last_enqueued_at, precision: 6
      t.timestamps precision: 6
    end
    add_index :submission_groups, :token, unique: true
    add_index :submission_groups, :idempotency_key, unique: true

    create_table :submission_group_cases do |t|
      t.references :submission_group, null: false, foreign_key: true
      t.references :submission, null: false, foreign_key: true, index: {unique: true}
      t.bigint :case_id, null: false
      t.integer :position, null: false
      t.text :shared_input
      t.string :state, null: false, default: "queued"
      t.string :attempt_token
      t.datetime :started_at, precision: 6
      t.datetime :finished_at, precision: 6
      t.timestamps precision: 6
    end
    add_index :submission_group_cases, [:submission_group_id, :case_id],
              unique: true, name: "group_case_identity"
    add_index :submission_group_cases, [:submission_group_id, :position],
              unique: true, name: "group_case_order"
  end
end
