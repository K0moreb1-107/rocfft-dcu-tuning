"""Resolve a separately submitted pure build for independent validation."""
import copy
import json
import re

from tools.workspace_manager import manager as mgr


def inputs(cfg):
    spec = cfg['pending_build_validation']
    mgr.require(isinstance(spec, dict) and set(spec) ==
                {'build_config', 'build_config_sha256', 'build_job_id'},
                'invalid pending-build validation specification')
    path = mgr.inside(spec['build_config'])
    mgr.require(re.fullmatch(r'[0-9a-f]{64}', spec['build_config_sha256'] or '')
                and mgr.common.sha(path) == spec['build_config_sha256'],
                'submitted build configuration differs')
    build = mgr.load(path)
    bp = mgr.locations(build, 'build')
    mgr.require(path == bp['run']/'submit-manifest.json', 'use the actually submitted build config')
    mgr.require(build['experiment'] == cfg['experiment']
                and build['build'].get('component', 'rocfft') == 'rocfft'
                and not build.get('post_build_validation'),
                'independent validation requires a pure rocFFT build')
    mgr.require(cfg['build'] == build['build'], 'validation selects another declared build')
    job = spec['build_job_id']
    receipt = json.loads((bp['run']/'submission.json').read_text(encoding='utf-8'))
    mgr.require(re.fullmatch(r'[1-9][0-9]*', job or '')
                and receipt['job'].split(';')[0] == job, 'pending build job differs from receipt')
    mgr.require(cfg['resources'].get('dependency') == 'afterok:'+job,
                'independent validation requires the successful build dependency')
    record = bp['run']/'build-provenance.json'
    mgr.require(mgr.inside(cfg['existing_build_validation']['build_record']) == record,
                'validation must select exactly its submitted pending build')
    return spec, build, bp, record


def resolve(cfg, allow_pending=False):
    spec, build, bp, path = inputs(cfg)
    if allow_pending and not path.exists():
        return dict(pending=True, component='rocfft', experiment=cfg['experiment'],
                    job_id=spec['build_job_id'], plan=dict(paths={k: str(v) for k, v in bp.items()}),
                    arm=dict(install=str(bp['install']),
                             source_repo=str(mgr.inside(build['build']['source_repo'], allow_root=True)),
                             source_commit=build['build']['source_commit'], source_state=None,
                             library_sha256=None, build_provenance=str(path)))
    built = json.loads(path.read_text(encoding='utf-8'))
    mgr.require(built.get('complete') is True and built.get('component') == 'rocfft'
                and built.get('experiment') == cfg['experiment']
                and built.get('job_id') == spec['build_job_id'],
                'pending build is incomplete, failed, or belongs to another job')
    arm = built['arm']
    identity = built['plan']['source_identity']
    mgr.require(arm['install'] == str(bp['install']) and arm['build_provenance'] == str(path)
                and arm['source_repo'] == str(mgr.inside(build['build']['source_repo'], allow_root=True))
                and identity['repo'] == arm['source_repo']
                and identity['source'] == str(mgr.inside(build['build']['source_dir']))
                and identity['commit'] == arm['source_commit']
                and identity.get('requested_commit', identity['commit']) == build['build']['source_commit']
                and built['plan']['paths'] == {k: str(v) for k, v in bp.items()}
                and built['plan'].get('post_build_validation_command') is None,
                'pending build source or installation identity differs')
    # Requested and recorded starting commits are distinct provenance fields.
    # No working-tree comparison or build-time source freeze is introduced here.
    mgr.require(mgr.common.sha(bp['install']/'lib/librocfft.so.0.1') == arm['library_sha256'],
                'pending build library differs from its actual record')
    return built


def measurement_preview(cfg, build, validation, reference_builds=None, validation_arm='candidate'):
    """Validate a future candidate selection without inventing its library hash."""
    protocol = mgr.measurement_protocol(cfg)
    mgr.require(cfg.get('policy') == 'FFT-event-cufft261012-single-v3'
                and cfg.get('timing_source_sha256') == protocol.SOURCE_SHA,
                'pending measurement requires the registered v3 timing source')
    selected = protocol.arms(cfg)
    mgr.require(validation_arm in selected and validation_arm in ('candidate', 'previous', 'unfused_cc'),
                'invalid pending validation arm')
    cases = mgr.common.cases(cfg)
    protocol.iterations(cfg)
    expected = {'build_record': validation['existing_build_validation']['build_record']}
    mgr.require(cfg['arms'][validation_arm] == expected,
                'measurement selects another pending candidate' if validation_arm == 'candidate'
                else 'measurement selects another pending validation arm')
    references = {}
    pending_references = {}
    reference_builds = reference_builds or {}
    mgr.require(set(reference_builds) <= set(selected) - {validation_arm, 'official', 'baseline'},
                'invalid pending reference arm')
    fields = ('install', 'source_repo', 'source_commit', 'source_state',
              'library_sha256', 'build_provenance')
    for name in selected:
        if name == validation_arm:
            continue
        if name in reference_builds:
            item = reference_builds[name]
            expected_reference = {'build_record': item['validation']['existing_build_validation']['build_record']}
            mgr.require(cfg['arms'][name] == expected_reference,
                        'measurement selects another pending reference: '+name)
            pending_references[name] = copy.deepcopy(item['built']['arm'])
            continue
        arm = copy.deepcopy(cfg['arms'][name])
        if arm.get('registry_id'):
            registered = mgr.registry()['installations'][arm['registry_id']]
            mgr.require(registered.get('role') == name and registered.get('eligible_formal_arm'),
                        'ineligible pending-measurement reference: '+name)
            for field in fields:
                mgr.require(arm.get(field, registered['arm'][field]) == registered['arm'][field],
                            'conflicting reference identity: '+name+'.'+field)
                arm[field] = registered['arm'][field]
            arm.pop('registry_id')
        mgr.require(all(field in arm for field in fields), 'incomplete reference: '+name)
        if name == 'official':
            mgr.require(arm['source_commit'] == protocol.OFFICIAL_COMMIT
                        and arm['library_sha256'] == protocol.OFFICIAL_SHA,
                        'fixed official identity differs in pending measurement')
        mgr.require(mgr.common.sha(mgr.inside(arm['install'])/'lib/librocfft.so.0.1') == arm['library_sha256'],
                    'pending-measurement reference library differs: '+name)
        references[name] = arm
    pinned = protocol.freeze_reference(cfg) if hasattr(protocol, 'freeze_reference') else copy.deepcopy(cfg)
    # Full concrete manifest validation occurs after the build and acceptance.
    # Keep this symbolic candidate out of the formal worker and registry.
    return dict(pending_build=True, formal=True, node_exclusive=True,
                paths={k: str(v) for k, v in mgr.locations(cfg, 'measure').items()},
                processes=len(protocol.schedule(cfg)), cases=len(cases),
                timing_warmups=protocol.WARMUPS, event_iterations=protocol.iterations(cfg),
                resolved_preregistration=pinned, reference_arms=references,
                pending_reference_arms=pending_references,
                pending_candidate=copy.deepcopy(build['arm']) if validation_arm == 'candidate' else None,
                validation_arm=validation_arm,
                pending_validation_arm=copy.deepcopy(build['arm']))
