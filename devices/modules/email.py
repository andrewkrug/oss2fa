from __future__ import unicode_literals

import logging

from rest_framework import serializers

from challenge.models import Challenge
from contrib.models import Module
from core import errors
from devices.models import Device
from enrollment.models import Enrollment
from .base import DeviceKindModule

logger = logging.getLogger(__name__)


class EmailDeviceEnrollmentCompleteRequest(serializers.Serializer):
    token = serializers.CharField()


class EmailDeviceEnrollmentPrepareRequest(serializers.Serializer):
    address = serializers.EmailField()


class EmailDeviceChallengeCompleteRequest(serializers.Serializer):
    token = serializers.CharField()


class EmailDeviceDetails(serializers.Serializer):
    address = serializers.EmailField()


class EmailDeviceChallengePrivateDetails(serializers.Serializer):
    token = serializers.CharField()


class EmailDeviceEnrollmentPrivateDetails(serializers.Serializer):
    address = serializers.EmailField()
    token = serializers.CharField()


class EmailDeviceKindModuleConfiguration(serializers.Serializer):
    from_email = serializers.EmailField()
    subject = serializers.CharField()
    message = serializers.CharField()
    html_message = serializers.CharField(required=False)
    communication_module = serializers.CharField()
    communication_module_settings = serializers.JSONField()


class EmailDeviceKindModule(DeviceKindModule):
    @staticmethod
    def mask_address(value):
        return value.split('@', 1)[1].lower()


    def _send_secure_token(self, address, policy, device_kind_options):
        # get instance of the communication module
        mdl = Module.objects.filter(
            name=device_kind_options['communication_module']).first()
        if not mdl:
            return None, errors.MFAMissingInformationError(
                'communication module `{0}` does not exist'.format(
                    device_kind_options['communication_module']))

        # generate a secret token
        tk = DeviceKindModule.generate_secure_token(policy)

        # obtain the module request model
        mdl_instance = mdl.get_instance()
        req = mdl_instance.get_request_model(data={
            'from_email':
            device_kind_options['from_email'],
            'recipient':
            address,
            'subject':
            device_kind_options['subject'],
            'message':
            device_kind_options['message'].format(token=tk),
            'html_message':
            device_kind_options['html_message'].format(token=tk),
        })

        if not req.is_valid():
            return False, errors.MFAMissingInformationError(
                'email communication module is not compatible: {0}'.format(
                    ','.join(req.errors)))

        # delegate sending email
        success, err = mdl_instance.execute(req)
        if err:
            return None, err

        if not success:
            return None, errors.MFAError(
                'could not send email through module `{0}`'.format(
                    device_kind_options['communication_module']))

        return tk, None

    def get_configuration_model(self, data):
        return DeviceKindModule.build_model_instance(
            EmailDeviceKindModuleConfiguration, data)

    def get_enrollment_prepare_model(self, data):
        return DeviceKindModule.build_model_instance(
            EmailDeviceEnrollmentPrepareRequest, data)

    def get_device_details_model(self, data):
        return DeviceKindModule.build_model_instance(EmailDeviceDetails, data)

    def get_enrollment_completion_model(self, data):
        return DeviceKindModule.build_model_instance(
            EmailDeviceEnrollmentCompleteRequest, data)

    def get_challenge_completion_model(self, data):
        return DeviceKindModule.build_model_instance(
            EmailDeviceChallengeCompleteRequest, data)

    def get_enrollment_public_details_model(self, data):
        return None

    def get_enrollment_private_details_model(self, data):
        return DeviceKindModule.build_model_instance(
            EmailDeviceEnrollmentPrivateDetails, data)

    def enrollment_prepare(self, enrollment):
        # get the email address from the device selection.
        prep_options, err = self.get_enrollment_prepare_model(
            enrollment.device_selection.options)
        if err:
            return  errors.MFAInconsistentStateError(
                'expected enrollment preparation information to be valid')

        # get the device kind details
        device_kind_options, err = self.get_configuration_model(
            enrollment.device_selection.kind.configuration)
        if err:
            return err

        # generate and send the token
        tk, err = self._send_secure_token(
            prep_options['address'], enrollment.policy, device_kind_options)

        if err:
            logger.error('failed to send secure token: {0}'.format(err))
            return None

        # store token for future need
        private_details = EmailDeviceEnrollmentPrivateDetails(
            data={'token': tk,
                  'address': prep_options['address']})

        assert private_details.is_valid()
        enrollment.private_details = private_details.validated_data

        return None

    def enrollment_complete(self, enrollment, data):
        assert enrollment.status == Enrollment.STATUS_IN_PROGRESS
        assert not enrollment.is_expired()

        # compare given token to privately stored token
        private_details = EmailDeviceEnrollmentPrivateDetails(
            data=enrollment.private_details)
        if not private_details.is_valid():
            return None, errors.MFAInconsistentStateError(
                'enrollment private details is invalid: {0}'.format(
                    private_details.errors))

        # if the token don't match, fail.
        if private_details.validated_data['token'] != data['token']:
            return None, errors.MFASecurityError(
                'token mismatch, expected `{0}` however received `{1}`'.format(
                    private_details.validated_data['token'], data['token']))

        # extract the device details
        details = EmailDeviceDetails(
            data={'address': private_details.validated_data['address']})

        assert details.is_valid()

        # create the device
        device = Device()

        device.name = u'Email [@{0}]'.format(
            EmailDeviceKindModule.mask_address(private_details.validated_data[
                'address']))

        device.kind = enrollment.device_selection.kind
        device.enrollment = enrollment

        # save the device details
        device.details = details.validated_data

        return device, None

    def challenge_create(self, challenge):
        # make sure we are processing challenges in the right state.
        assert challenge.status == Challenge.STATUS_NEW

        # obtain the device information
        device, err = challenge.device.get_model()
        if err:
            return False, err

        # get the device kind details
        device_kind_options, err = self.get_configuration_model(
            challenge.device.kind.options)
        if err:
            return False, err

        # create and end token
        tk, err = self._send_secure_token(device['address'], challenge.policy,
                                          device_kind_options)
        if err:
            return False, err

        # store for future use
        private_details = EmailDeviceChallengePrivateDetails(
            data={'token': tk})

        assert private_details.is_valid()

        return True, None

    def challenge_complete(self, challenge, data):
        assert challenge.status == Challenge.STATUS_IN_PROGRESS

        # get the private challenge details; fail if we can't validate
        serializer = EmailDeviceChallengePrivateDetails(
            data=challenge.private_details)
        if not serializer.is_valid():
            return False, errors.MFAMissingInformationError(serializer.errors)

        details = serializer.validated_data

        # compare the tokens
        if details['token'] != data['token']:
            logger.error('token `{0}` is not valid for challenge `{1}`'.format(
                data['token'], challenge.pk))
            return False, None

        return True, None
