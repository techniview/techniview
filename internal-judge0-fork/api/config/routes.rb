Rails.application.routes.draw do
  post "internal/submission-groups", to: "submission_groups#create"
  get "internal/submission-groups/by-key/:key", to: "submission_groups#by_key"
  get "internal/submission-groups/:token", to: "submission_groups#show"
  resources :submissions, only: [:show, :create], param: :token
  get "about", to: "info#about"
  get "workers", to: "health#workers"
end
