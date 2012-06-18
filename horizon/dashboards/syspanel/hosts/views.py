import logging
import simplejson

from django.http import HttpResponse
from django.utils.datastructures import SortedDict
from django.utils.translation import ugettext_lazy as _

from horizon import views
from horizon.api.monitoring import monitorclient
from horizon.api.monitoring import metricsclient
from horizon import api
from horizon import exceptions
from horizon import tables

LOG = logging.getLogger(__name__)

def _get_host_dict(request, host):
    host_dict = {}
    host_dict['name'] = host

    # Check overall health
    host_dict['state'] = monitorclient().get_overall_state(host)
    if host_dict['state'] == 1:
        host_dict['class'] = 'host_ok'
    elif host_dict['state'] == 0:
        host_dict['class'] = 'host_warn'
    else:
        host_dict['class'] = 'host_error'

    # Get errors, warnings and notices
    host_dict['errors'] = monitorclient().get_errors(host)
    host_dict['warnings'] = monitorclient().get_warnings(host)
    host_dict['notices'] = monitorclient().get_notices(host)

    return host_dict

def _get_host_cpu_dict(request, host, core=None):
    host_dict = {}

    # get cpu stats and load
    host_dict['cpu_load'] = monitorclient().get_cpu_load(host)
    host_dict['cores'] = monitorclient().get_cpu_cores(host)
    host_dict['cpu_speed'] = monitorclient().get_cpu_speed(host)

    if host_dict['cpu_load'] > 90:
        host_dict['cpu_class'] = 'progress-danger'
    elif host_dict['cpu_load'] > 60:
        host_dict['cpu_class'] = 'progress-warning'
    else:
        host_dict['cpu_class'] = 'progress-success'

    return host_dict

def _get_host_mem_dict(request, host):
    host_dict = {}

    # Get memory stats and load
    host_dict['total_mem'] = monitorclient().get_total_memory(host)
    host_dict['mem_usage'] = monitorclient().get_mem_usage(host)
    host_dict['mem_used'] = (float(host_dict['mem_usage'])/float(100)) * host_dict['total_mem']

    if host_dict['mem_usage'] > 90:
        host_dict['mem_class'] = 'progress-danger'
    elif host_dict['mem_usage'] > 60:
        host_dict['mem_class'] = 'progress-warning'
    else:
        host_dict['mem_class'] = 'progress-success'

    return host_dict

def _get_host_part_dict(request, host):
    parts_ret = []

    parts = monitorclient().get_monitored_partitions(host)
    for part in parts:
        part_dict = {}

        stats = monitorclient().get_partition_stats(host, part)
        part_dict['name'] = part
        part_dict['total'] = stats['total']
        part_dict['used'] = stats['used']
        
        parts_ret.append(part_dict)

    part_dict['parts'] = parts_ret

    return part_dict

def _get_host_net_dict(request, host, iface=None):
    net_ret = []
    ints = []

    ints = monitorclient().get_monitored_interfaces(host)

    tband = 0
    ttx = 0
    trx = 0
    tused = 0
    tclass = ''

    for interface in ints:
        int_dict = {}

        int_det = monitorclient().get_interface_stats(host, interface)
        int_dict['name'] = interface

        int_dict['bandwidth'] = int_det['bandwidth']
        tband += int_det['bandwidth']
        int_dict['rx'] = int_det['rx']
        trx += int_det['rx']
        int_dict['tx'] = int_det['tx']
        ttx += int_det['tx']
        int_dict['used'] = int_det['used']
        tused += (float(int_det['used'])/float(100)) * int_det['bandwidth']

        if int_dict['used'] > 90:
            int_dict['class'] = 'progress-danger'
        elif int_dict['used'] > 60:
            int_dict['class'] = 'progress-warning'
        else:
            int_dict['class'] = 'progress-success'
        
        if iface == None or iface == interface:
            net_ret.append(int_dict)

        tused = int((tused/tband) * 100)
        
        if tused > 90:
            tclass = 'progress-danger'
        elif tused > 60:
            tclass = 'progress-warning'
        else:
            tclass = 'progress-success'
    
    if iface == None or iface == 'All':
        net_ret.append({
            'bandwidth': tband,
            'tx': ttx,
            'rx': trx,
            'used': tused,
            'class': tclass
        })

    return net_ret

class HostsView(views.APIView):
    template_name = 'syspanel/hosts/index.html'

    def get_data(self, request, context, *args, **kwargs):
        host_list = {}
        hosts = []

        for i, service in enumerate(request.user.service_catalog):
            service_obj = api.keystone.Service(service)
            host_list[service_obj.host] = 1

        host_list = {
            '64.102.251.71': 1,
            '64.102.251.72': 1,
            '64.102.251.73': 1,
            '64.102.251.74': 1,
            '64.102.251.75': 1,
            '64.102.251.76': 1,
            '64.102.251.77': 1,
            '64.102.251.78': 1,
            '64.102.251.79': 1,
        }

        for host in sorted(host_list.keys()):
            host_gen_dict = _get_host_dict(request, host)
            host_cpu_dict = _get_host_cpu_dict(request, host)
            host_mem_dict = _get_host_mem_dict(request, host)
            host_dict = dict(host_gen_dict.items() +
                             host_cpu_dict.items() +
                             host_mem_dict.items())
            hosts.append(host_dict)

        context['hosts'] = hosts
        return context


class HostDetailView(views.APIView):
    template_name = 'syspanel/hosts/details.html'

    def get_data(self, request, context, *args, **kwargs):
        host = kwargs['host_id']
        # Get host dictionaries
        host_dict = _get_host_dict(request, host)
        host_dict['cpu'] = _get_host_cpu_dict(request, host)
        host_dict['mem'] = _get_host_mem_dict(request, host)
        host_dict['part'] = _get_host_part_dict(request, host)
        net_dict = _get_host_net_dict(request, host)
        tot_net_stats = net_dict.pop()
        host_dict['net'] = net_dict
        host_dict['net_total'] = tot_net_stats
        
        # Get available host graphs
        host_dict['cpu_graph'] = metricsclient().get_cpu_graph(host)
        host_dict['mem_graph'] = metricsclient().get_mem_graph(host)
        host_dict['net_graph'] = metricsclient().get_network_graph(host)

        context['host'] = host_dict

        return context

class NetStatsView(views.APIView):
   def get(self, request, *args, **kwargs):
        host = kwargs['host_id']
        interface = kwargs['int_id']
        if interface == 'all':
            interface = None

        message = {}
        if request.is_ajax():
            message['graph'] = metricsclient().get_network_graph(host, interface)
            message['stats'] = _get_host_net_dict(request, host, interface)
        else:
            message['error'] = "Not a valid XMLHttpRequest"

        return HttpResponse(simplejson.dumps(message), mimetype='application/json')

class CpuStatsView(views.APIView):
   def get(self, request, *args, **kwargs):
        host = kwargs['host_id']
        core = kwargs['cpu_id']
        if interface == 'all':
            interface = None

        message = {}
        if request.is_ajax():
            message['graph'] = metricsclient().get_cpu_graph(host, core)
            message['stats'] = _get_host_net_dict(host, interface)
        else:
            message['error'] = "Not a valid XMLHttpRequest"

        return HttpResponse(message, mimetype='application/text')

class MemStatsView(views.APIView):
   def get(self, request, *args, **kwargs):
        host = kwargs['host_id']
        dimm = kwargs['mem_id']
        if interface == 'all':
            interface = None

        message = {}
        if request.is_ajax():
            message['graph'] = metricsclient().get_network_graph(host, interface)
            message['stats'] = _get_host_net_dict(host, interface)
        else:
            message['error'] = "Not a valid XMLHttpRequest"

        return HttpResponse(message, mimetype='application/text')

class DiskStatsView(views.APIView):
   def get(self, request, *args, **kwargs):
        host = kwargs['host_id']
        interface = kwargs['int_id']
        if interface == 'all':
            interface = None

        message = {}
        if request.is_ajax():
            message['graph'] = metricsclient().get_network_graph(host, interface)
            message['stats'] = _get_host_net_dict(request, host, interface)
        else:
            message['error'] = "Not a valid XMLHttpRequest"

        return HttpResponse(message, mimetype='application/text')