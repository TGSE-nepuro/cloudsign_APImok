from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, View
from django.urls import reverse_lazy
from django.shortcuts import render, redirect, get_object_or_404
from .models import Project, CloudSignConfig
from .forms import CloudSignConfigForm # Will create this form next

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

class CloudSignConfigView(View):
    template_name = 'projects/cloudsignconfig_form.html'

    def get(self, request, *args, **kwargs):
        config = CloudSignConfig.objects.first()
        form = CloudSignConfigForm(instance=config)
        return render(request, self.template_name, {'form': form})

    def post(self, request, *args, **kwargs):
        config = CloudSignConfig.objects.first()
        form = CloudSignConfigForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            return redirect(reverse_lazy('projects:cloudsign_config')) # Redirect to itself after save
        return render(request, self.template_name, {'form': form})