from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from .models import Project

class ProjectListView(ListView):
    model = Project
    template_name = 'projects/project_list.html'
    context_object_name = 'projects'

class ProjectDetailView(DetailView):
    model = Project
    template_name = 'projects/project_detail.html'
    context_object_name = 'project'

class ProjectCreateView(CreateView):
    model = Project
    template_name = 'projects/project_form.html'
    fields = ['title', 'description', 'cloudsign_document_id']
    success_url = reverse_lazy('projects:project_list')

class ProjectUpdateView(UpdateView):
    model = Project
    template_name = 'projects/project_form.html'
    fields = ['title', 'description', 'cloudsign_document_id']
    success_url = reverse_lazy('projects:project_list')

class ProjectDeleteView(DeleteView):
    model = Project
    template_name = 'projects/project_confirm_delete.html'
    success_url = reverse_lazy('projects:project_list')