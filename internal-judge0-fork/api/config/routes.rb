Rails.application.routes.draw do
  resources :submissions, only: [:show, :create], param: :token
  get "about", to: "info#about"
  get "workers", to: "health#workers"
end
