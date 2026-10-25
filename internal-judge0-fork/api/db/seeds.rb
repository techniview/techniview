require_relative "languages/active"
ActiveRecord::Base.transaction do
  Language.unscoped.where.not(id: @languages.map { |language| language.fetch(:id) })
    .update_all(is_archived: true)
  @languages.each do |attributes|
    language = Language.unscoped.find_or_initialize_by(id: attributes.fetch(:id))
    language.update!(attributes)
  end
end
